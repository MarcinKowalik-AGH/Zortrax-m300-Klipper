#!/usr/bin/env python3
"""Plan/apply/rollback M300 R16.12 native R15.3-compatible update, 180C homing and separate TEST UI."""
import argparse
import ast
import base64
import configparser
import datetime
import fnmatch
import glob
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent
_profile_spec = importlib.util.spec_from_file_location('m300_update_profile', HERE / 'm300_profile.py')
profile = importlib.util.module_from_spec(_profile_spec)
_profile_spec.loader.exec_module(profile)
NAMES = ('m300_display.py', 'm300_display_stream.py', 'm300_display_oem.py',
         'm300_display_moon.json', 'm300_menu.py')
NAMES += ('m300_ui_m11_state.py', 'm300_mcu.py', 'm300_hardware.py',
          'm300_motion.py', 'm300_calibration.py', 'm300_native_motion.py',
          'm300_menu_ui.py', 'm300_lifecycle.py')
NAMES += ('m300_calibration_state.py', 'm300_leveling_state.py',
          'm300_leveling_ui.py', 'm300_procedures.py', 'm300_oem_graphics.py',
          'm300_material_ui_state.py', 'm300_ui_labels.py')
NAMES += ('m300_leveling_oem.py', 'm300_leveling_oem_131.json',
          'm300_oem_sprites_131.json', 'm300_oled.py',
          'm300_oled_transport.py', 'm300_oled_render.py')
NAMES += ('m300_filament.py', 'm300_filament_state.py')
NAMES += ('m300_native_service.py', 'm300_maintenance.py',
          'm300_native_maintenance.py', 'm300_oem_procedure_ui.py')
NAMES += ('m300_settings.py', 'm300_settings_ui.py', 'm300_browser.py', 'm300_browser_state.py', 'm300_job.py')
NAMES += ('m300_fans.py', 'm300_native_fans.py', 'm300_maintenance_ui.py')
NAMES += ('m300_native_probe.py', 'm300_native_z.py', 'm300_stock_geometry.py', 'm300_nvm.py')
NAMES += ('m300_models.py', 'm300_sd.py', 'm300_fat.py', 'm300_binary.py',
          'm300_zcode.py', 'm300_job_sd.py')
NAMES += ('m300_print_ui.py', 'm300_print_hold.py', 'm300_resources.py')
CONFIG_FILES = ('klipper_calibration.cfg', 'm300_operations.cfg', 'm300_tests.cfg')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify():
    manifest = json.loads((HERE / 'MANIFEST.json').read_text())
    for rel, expected in manifest.items():
        p = HERE / rel
        if not p.is_file() or digest(p.read_bytes()) != expected:
            raise ValueError('Package integrity mismatch: ' + rel)
    return len(manifest)


def check_api(root):
    for rel, cls, methods in (
        ('klippy/extras/m300_oled_transport.py', 'OledStream',
         {'step', 'ack', 'start', 'stop', 'request'}),
        ('klippy/extras/m300_oled_transport.py', 'FastOledStream',
         {'step', 'ack', 'next_wakeup'}),
        ('klippy/extras/m300_oled.py', 'M300OLED', {'_panel', '_tick', '_send_one'}),
        ('klippy/extras/m300_oled_render.py', 'Frame',
         {'text', 'original_sprite', 'wire_bytes'}),
        ('klippy/extras/virtual_sdcard.py', 'VirtualSD',
         {'do_resume', '_reset_file', 'work_handler'}),
        ('klippy/webhooks.py', 'WebHooks', {'register_endpoint'}),
        ('klippy/mcu.py', 'MCURestartHelper', {'_check_restart'})):
        p = root / rel
        tree = ast.parse(p.read_text())
        node = next((n for n in tree.body
                     if isinstance(n, ast.ClassDef) and n.name == cls), None)
        if node is None or not methods <= {
                n.name for n in node.body if isinstance(n, ast.FunctionDef)}:
            raise ValueError('Unsupported host API: ' + rel)
    oled = (root / 'klippy/extras/m300_oled.py').read_text()
    wh = (root / 'klippy/webhooks.py').read_text()
    if "m300:panel" not in oled or '_endpoints' not in wh:
        raise ValueError('Missing M300 panel / Klipper API capability')
    ui = (root / 'klippy/extras/m300_ui_m11_state.py').read_text()
    # The old motion/menu modules are replaced atomically below. R15.3 has
    # no HOMING_UI_ABI; its exact known hashes, not a newer API marker, govern
    # upgrade eligibility. Keep checking the presentation API actually used.
    if 'def require_rows(' not in ui:
        raise ValueError('M300 M11 presentation support required')


def validate_settings(data):
    parser = configparser.ConfigParser(inline_comment_prefixes=('#', ';'))
    parser.read_string(data.decode())
    if parser.sections() != ['m300_display']:
        raise ValueError('m300_display.cfg must only contain [m300_display]')
    section = parser['m300_display']
    if set(section) - {'timeout', 'normal_contrast', 'dim_contrast', 'notice_seconds'}:
        raise ValueError('Unknown display setting')
    timeout = section.getfloat('timeout', 300)
    normal = section.getint('normal_contrast', 159)
    dim = section.getint('dim_contrast', 32)
    notice = section.getfloat('notice_seconds', 10)
    if not (5 <= timeout <= 86400 and 1 <= dim <= normal <= 159 and 1 <= notice <= 60):
        raise ValueError('Invalid display timeout/contrast')


def already_included(config, settings):
    seen, pending, included = set(), [config], False
    while pending:
        path = pending.pop().resolve()
        if path in seen or path == settings.resolve():
            continue
        seen.add(path)
        text = path.read_text()
        if re.search(r'(?mi)^\s*\[m300_display\]\s*$', text):
            raise ValueError('Existing inline [m300_display]: ' + str(path))
        for pattern in re.findall(r'(?mi)^\s*\[include\s+([^\]]+)\]', text):
            absolute = str((path.parent / pattern.strip()).resolve())
            if fnmatch.fnmatchcase(str(settings.resolve()), absolute):
                included = True
            pending.extend(Path(p) for p in glob.glob(absolute)
                           if Path(p).is_file())
    return included


def plan(root, config):
    root, config = root.resolve(), config.resolve()
    check_api(root)
    if not config.is_file():
        raise ValueError('Missing printer.cfg: ' + str(config))
    extras = root / 'klippy/extras'
    desired = {extras / name: (HERE / 'payload' / name).read_bytes()
               for name in NAMES}
    baselines = json.loads((HERE / 'SUPPORTED_BASELINES.json').read_text())
    for p, data in desired.items():
        if p.name == 'm300_menu.py' and not p.is_file():
            raise ValueError('An installed native M300 menu is required')
        if (p.exists() and p.read_bytes() != data
                and digest(p.read_bytes()) not in baselines.get(p.name, [])):
            raise ValueError('Existing unknown M300 runtime module: ' + str(p))
    settings = config.parent / 'm300_display.cfg'
    settings_data = settings.read_bytes() if settings.exists() else (
        HERE / 'payload/m300_display.cfg').read_bytes()
    validate_settings(settings_data)
    desired[settings] = settings_data
    tree = profile.read_tree(config)
    for path, text in tree.items():
        if not path.is_relative_to(config.parent):
            raise ValueError('Configuration include outside printer config directory: ' + str(path))
        desired[path] = profile.convert_text(text).encode()
    existing = {name.lower() for path in tree for name, _ in
                profile.blocks(desired[path].decode())[1]}
    additions = []
    for name in CONFIG_FILES:
        target = config.parent / name
        if target not in desired:
            if target.exists():
                desired[target] = profile.convert_text(target.read_text()).encode()
            else:
                text = profile.missing_macros((HERE / 'payload' / name).read_text(), existing)
                desired[target] = profile.convert_text(text).encode()
        existing.update(n.lower() for n, _ in profile.blocks(desired[target].decode())[1])
        extra = profile.convert_text(
            profile.missing_macros((HERE / 'payload' / name).read_text(), existing))
        if profile.blocks(extra)[1]:
            desired[target] += ('\n' + extra).encode()
            existing.update(n.lower() for n, _ in profile.blocks(extra)[1])
        if not any(fnmatch.fnmatchcase(str(target), str((path.parent / section[8:].strip()).resolve()))
                   for path, content in tree.items()
                   for section, _ in profile.blocks(content)[1]
                   if section.lower().startswith('include ')):
            additions.append('[include ' + name + ']\n')
    text = desired[config].decode()
    if not already_included(config, settings):
        additions.append('[include m300_display.cfg]\n')
    if 'm300_motion' in existing and 'idle_timeout' not in existing:
        additions.append('\n[idle_timeout]\n' + profile.IDLE_GCODE)
    if additions:
        addition = '\n# M300 R16.12 native R15.3-compatible update and separate TEST macros\n' + ''.join(additions) + '\n'
        marker = re.search(r'(?m)^#\*#.*SAVE_CONFIG', text)
        at = marker.start() if marker else len(text)
        text = text[:at] + addition + text[at:]
    desired[config] = text.encode()
    return [(p, p.read_bytes() if p.exists() else None, data)
            for p, data in desired.items()
            if not p.exists() or p.read_bytes() != data]


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o644
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(root, config, changes):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = root / ('host_r16_backup_' + stamp)
    folder.mkdir(mode=0o700)
    receipt = folder / 'RECEIPT.json'
    doc = {'root': str(root.resolve()), 'config': str(config.resolve()),
           'state': 'PREPARED', 'changes': []}
    for p, old, new in changes:
        doc['changes'].append({
            'path': str(p), 'before': base64.b64encode(old).decode()
            if old is not None else None, 'after_sha256': digest(new)})
    receipt.write_text(json.dumps(doc, indent=2) + '\n')
    os.chmod(receipt, 0o600)
    written = []
    try:
        for p, old, new in changes:
            current = p.read_bytes() if p.exists() else None
            if current != old:
                raise ValueError('File changed since plan: ' + str(p))
            atomic_write(p, new)
            written.append((p, old))
    except BaseException:
        for p, old in reversed(written):
            if old is None:
                p.unlink()
            else:
                atomic_write(p, old)
        doc['state'] = 'ROLLED_BACK'
        receipt.write_text(json.dumps(doc, indent=2) + '\n')
        raise
    doc['state'] = 'APPLIED'
    receipt.write_text(json.dumps(doc, indent=2) + '\n')
    return receipt


def rollback(receipt, root, config):
    doc = json.loads(receipt.read_text())
    if doc['root'] != str(root.resolve()) or doc['config'] != str(config.resolve()):
        raise ValueError('Receipt does not match installation paths')
    allowed = {root.resolve() / 'klippy/extras' / name for name in NAMES}
    allowed |= {Path(row['path']).resolve() for row in doc['changes']
                if Path(row['path']).suffix == '.cfg'
                and Path(row['path']).resolve().is_relative_to(config.parent.resolve())}
    entries = []
    for row in doc['changes']:
        p = Path(row['path'])
        if p.resolve() not in allowed:
            raise ValueError('Receipt contains unexpected path')
        before = base64.b64decode(row['before']) if row['before'] is not None else None
        current = p.read_bytes() if p.exists() else None
        if current == before:
            continue
        if current is None or digest(current) != row['after_sha256']:
            raise ValueError('Refusing to replace subsequently edited file: ' + str(p))
        entries.append((p, before))
    for p, before in reversed(entries):
        if before is None:
            p.unlink()
        else:
            atomic_write(p, before)
    return len(entries)


def stopped():
    result = subprocess.run(['systemctl', 'is-active', 'klipper.service'],
                            capture_output=True, text=True)
    if result.stdout.strip() not in ('inactive', 'failed'):
        raise ValueError('Stop klipper.service before apply or rollback')


def paths(args):
    info = {}
    if args.root is None or args.config is None:
        try:
            with urllib.request.urlopen(
                    'http://127.0.0.1:7125/printer/info', timeout=3) as response:
                info = json.load(response).get('result', {})
        except Exception:
            pass
    home = Path.home()
    root = args.root or Path(info.get('klipper_path',
                  str(home / 'm300-test01-0.13.2/klipper')))
    config = args.config or Path(info.get('config_file',
                                         str(home / 'printer_data/config/printer.cfg')))
    return root.resolve(), config.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    try:
        verify()
        root, config = paths(args)
        if args.rollback:
            stopped()
            print(json.dumps({'status': 'ROLLED_BACK_R16',
                              'files': rollback(args.rollback, root, config)}))
            return
        changes = plan(root, config)
        result = {'status': 'PLAN_M300_R16_12' if changes else 'ALREADY_M300_R16_12',
                  'host_update': 'R16.12',
                  'root': str(root), 'config': str(config),
                  'files_changed': len(changes), 'files': [str(p) for p, _, _ in changes],
                  'MCU_changed': False, 'factory_Z_requires_MCU_R14_5': True,
                  'native_control_changed': True, 'z_homing_temperature': 180,
                  'xy_velocity_profile': 300,
                  'calibration_temperature': 260, 'filament_temperature': 240,
                  'service_started': False}
        if args.apply and changes:
            stopped()
            result['receipt'] = str(apply(root, config, changes))
            result['status'] = 'INSTALLED_M300_R16_12'
        print(json.dumps(result, indent=2))
    except Exception as exc:
        parser.exit(1, 'REFUSED: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
