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

GROUPS = ('Klipper', 'ZORTRAX M300', 'TEST M300')
TEST_NAMES = {'ZORTRAX_LOAD', 'ZORTRAX_UNLOAD', 'ZORTRAX_CHANGE', 'ZORTRAX_LEVEL',
              'ZORTRAX_PRINT', 'ZORTRAX_PROCEDURE', 'ZORTRAX_OLED_PERF',
              'ZORTRAX_TEST_PRINT_FAN', 'ZORTRAX_TEST_HOTEND_FAN',
              'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP'}


def category(name):
    name = name.upper()
    if name in TEST_NAMES or name.startswith(('TEST_M300_', 'ZORTRAX_TEST_')):
        return 'TEST M300'
    if name.startswith('PID_') or name in ('PAUSE', 'RESUME', 'CANCEL_PRINT',
                                          'START_PRINT', 'END_PRINT', 'COOLDOWN'):
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
        settings = request(args.moonraker, '/printer/objects/query?configfile')['status']['configfile']['settings']
        names = sorted(name[12:].upper() for name in settings if name.lower().startswith('gcode_macro '))
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
