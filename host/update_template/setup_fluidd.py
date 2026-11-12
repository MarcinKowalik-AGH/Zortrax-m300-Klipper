#!/usr/bin/env python3
"""Group M300 macros through Moonraker, preserving unrelated UI preferences."""
import argparse
import copy
import datetime
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid

from install import atomic_write
from m300_profile import MACRO_RENAMES, RETIRED_LEVEL_MACROS

GROUPS = ('Klipper', 'ZORTRAX M300')
TEST_NAMES = {'ZORTRAX_PRINT', 'ZORTRAX_OLED_PERF',
              'ZORTRAX_TEST_PRINT_FAN', 'ZORTRAX_TEST_HOTEND_FAN',
              'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP'}


def hidden_test(name):
    name = name.upper()
    return name in TEST_NAMES or name.startswith(('TEST_M300_', 'TEST_ZORTRAX_', 'ZORTRAX_TEST_'))


def category(name):
    name = name.upper()
    if hidden_test(name):
        return None
    if name.startswith('PID_') or name in ('BED_MESH', 'ZORTRAX_BED_MESH', 'ZORTRAX_PAD_MESH_STATUS',
                                          'M300_PAD_MESH_CALIBRATE', 'BED_MESH_CALIBRATE',
                                          'PAUSE', 'RESUME', 'CANCEL_PRINT',
                                          'START_PRINT', 'END_PRINT', 'FILAMENT_READY', 'M600', 'M601',
                                          'PRINT_CONTROL_STATUS', 'PAUSE_TEMP_STATUS', 'COOLDOWN'):
        return 'Klipper'
    if name.startswith('ZORTRAX_'):
        return 'ZORTRAX M300'
    return None


def merge_groups(before, names):
    after = copy.deepcopy(before)
    if not isinstance(after, dict):
        raise ValueError('Unsupported Fluidd macro settings')
    categories, stored = after.setdefault('categories', []), after.setdefault('stored', [])
    if not isinstance(categories, list) or not isinstance(stored, list):
        raise ValueError('Unsupported Fluidd category schema')
    if (any(not isinstance(c, dict) or not isinstance(c.get('id'), str)
            or not isinstance(c.get('name'), str) for c in categories)
            or len({c['id'] for c in categories}) != len(categories)):
        raise ValueError('Ambiguous Fluidd category identities')
    if any(not isinstance(m, dict) or not isinstance(m.get('name'), str) for m in stored):
        raise ValueError('Unsupported Fluidd stored macros')
    available = {n.upper() for n in names}
    stored[:] = [row for row in stored if row['name'].upper()
                 not in RETIRED_LEVEL_MACROS - available]
    for old, new in MACRO_RENAMES.items():
        old_rows = [m for m in stored if m['name'].upper() == old]
        new_rows = [m for m in stored if m['name'].upper() == new]
        if len(old_rows) > 1 or len(new_rows) > 1:
            raise ValueError('Duplicate Fluidd macro during name migration: ' + old)
        if new not in available or not old_rows:
            continue
        if new_rows:
            stored.remove(old_rows[0])
        else:
            old_rows[0]['name'] = new
    assignments = {name: category(name) for name in names if category(name) is not None}
    for group in GROUPS:
        relevant = [name for name in assignments if assignments[name] == group]
        if not relevant:
            continue
        matches = [c for c in categories if c['name'] == group]
        if len(matches) > 1:
            raise ValueError('Duplicate Fluidd category: ' + group)
        if matches:
            cid = matches[0]['id']
        else:
            cid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'https://zortrax-m300.local/macros/' + group))
            if any(c['id'] == cid for c in categories):
                raise ValueError('Fluidd category identity collision')
            categories.append({'id': cid, 'name': group})
        for name in relevant:
            rows = [m for m in stored if m['name'].upper() == name.upper()]
            if len(rows) > 1:
                raise ValueError('Duplicate Fluidd macro: ' + name)
            if rows:
                rows[0]['categoryId'] = cid
            else:
                stored.append({'name': name, 'categoryId': cid, 'visible': True})
    # Lab macros cannot reappear through stale browser preferences. Preserve
    # custom bodies on disk and their other display options, but hide them.
    stored[:] = [m for m in stored if not (hidden_test(m['name']) and m['name'].upper() not in available)]
    test_ids = {c['id'] for c in categories if c['name'] == 'TEST M300'}
    for name in names:
        if not hidden_test(name):
            continue
        rows = [m for m in stored if m['name'].upper() == name.upper()]
        if len(rows) > 1:
            raise ValueError('Duplicate Fluidd macro: ' + name)
        if not rows:
            stored.append({'name': name, 'visible': False, 'categoryId': '0'})
        else:
            rows[0]['visible'] = False
            if rows[0].get('categoryId') in test_ids:
                rows[0]['categoryId'] = '0'
    used = {m.get('categoryId') for m in stored}
    categories[:] = [c for c in categories if c['id'] not in test_ids or c['id'] in used]
    return after, assignments


def request(base, endpoint, data=None):
    req = urllib.request.Request(base.rstrip('/') + endpoint,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.load(response)['result']


def read_macros(base):
    try:
        return request(base, '/server/database/item?namespace=fluidd&key=macros')['value']
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        return {}


def configured_macro_names(configfile):
    # settings contains accessed options; config is the complete effective
    # configuration. Use both when new macros precede their settings snapshot.
    names = set()
    for source in ('config', 'settings'):
        sections = configfile.get(source, {})
        if not isinstance(sections, dict):
            raise ValueError('Unsupported Klipper configfile status: ' + source)
        names.update(name[12:].strip().upper() for name in sections
                     if isinstance(name, str) and name.lower().startswith('gcode_macro '))
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--moonraker', default='http://127.0.0.1:7125')
    parser.add_argument('--config-directory', type=Path,
                        default=Path.home() / 'printer_data/config')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    before = read_macros(args.moonraker)
    if args.rollback:
        backup = json.loads(args.rollback.read_text())
        if backup.get('namespace') != 'fluidd' or backup.get('key') != 'macros':
            raise ValueError('Not a Fluidd macro backup')
        if before != backup['after']:
            raise ValueError('Fluidd settings changed since this backup')
        after, assignments = backup['before'], {}
    else:
        configfile = request(args.moonraker, '/printer/objects/query?configfile')['status']['configfile']
        names = configured_macro_names(configfile)
        after, assignments = merge_groups(before, names)
    result = {'status': 'PLAN_FLUIDD_GROUPS' if before != after else 'ALREADY_FLUIDD_GROUPS',
              'groups': {group: sorted(name for name, g in assignments.items() if g == group) for group in GROUPS}}
    if args.apply and after != before:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = args.config_directory / ('m300_fluidd_groups_' + stamp + '.json')
        atomic_write(path, json.dumps({'namespace': 'fluidd', 'key': 'macros',
                                     'before': before, 'after': after}, indent=2).encode())
        path.chmod(0o600)
        if read_macros(args.moonraker) != before:
            raise ValueError('Fluidd settings changed during planning')
        saved = request(args.moonraker, '/server/database/item',
                        {'namespace': 'fluidd', 'key': 'macros', 'value': after})
        if saved.get('value') != after:
            raise ValueError('Moonraker did not confirm the macro groups; backup: ' + str(path))
        result.update(status='INSTALLED_FLUIDD_GROUPS', backup=str(path))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
