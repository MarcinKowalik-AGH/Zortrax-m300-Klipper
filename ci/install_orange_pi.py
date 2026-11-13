#!/usr/bin/env python3
"""Install the verified M300 Classic host and Fluidd on an existing Orange Pi."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

PACKAGE = Path(__file__).resolve().parent
MOONRAKER = 'http://127.0.0.1:7125'
DEFAULT_FLUIDD_PORT = 4480
INSTALL_STATE_NAME = '.m300-installer.json'
OLD_PAD_GEOMETRY_ERROR = 'pad widths and edge_margin must leave a positive inset (width <= 100 mm)'
BUGGY_MAINTENANCE_SHA256 = '16ca09b60c14c2503b5a77bce1c7f7b939938161b9953e55a4d06a9268da3a88'
BUSY_OBJECTS = ('m300_job', 'm300_motion', 'm300_filament',
                'm300_calibration', 'm300_maintenance', 'm300_pad_mesh', 'm300_nvm',
                'm300_sd', 'm300_thermal', 'm300_fans')
IDLE_QUERY = '/printer/objects/query?' + '&'.join((
    'print_stats=state', 'pause_resume=is_paused', 'idle_timeout=state', 'm300_print_control=busy,paused',
    'toolhead=print_time,estimated_print_time', 'extruder=target', 'heater_bed=target',
    *(name + '=busy' for name in BUSY_OBJECTS)))


def run(*args, capture=False, cwd=None):
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                            cwd=cwd)
    return result.stdout


def printer(endpoint):
    with urlopen(MOONRAKER + endpoint, timeout=5) as response:
        return json.load(response)['result']


def startup_status_failure(info):
    """Recognize only the exact R29 early-Moonraker software regression."""
    if info.get('state') != 'shutdown' or 'Unhandled exception during run' not in info.get('state_message',''):
        return False
    try:
        target=Path(info['klipper_path'])/'klippy/extras/m300_native_maintenance.py'
        if hashlib.sha256(target.read_bytes()).hexdigest()!=BUGGY_MAINTENANCE_SHA256:
            return False
        with Path(info['log_file']).open('rb') as stream:
            stream.seek(0,2);stream.seek(max(0,stream.tell()-512*1024))
            text=stream.read().decode(errors='replace')
        # Never authorize recovery from a traceback in an older session.
        session=text.rsplit('Start printer at ',1)[-1]
        return ('/extras/m300_native_maintenance.py' in session
                and "AttributeError: 'M300NativeMaintenance' object has no attribute 'hotend'" in session)
    except (OSError,KeyError,TypeError):
        return False


def require_idle(*,repair_startup=False):
    info = printer('/printer/info')
    if info['state'] != 'ready':
        if repair_startup:
            if startup_status_failure(info):return info
            raise ValueError('Startup repair requires the exact early-status R29 exception in the current session')
        # The preceding adapter rejected edge_margin=0 while reading config,
        # before MCU connection. Allow installing its fix from this one known
        # startup error; print_stats does not exist yet in that state. This
        # never accepts a runtime shutdown, active print or unknown error.
        if info['state'] == 'error' and OLD_PAD_GEOMETRY_ERROR in info.get('state_message',''):
            return info
        raise ValueError('Wait until Klipper is Ready and the printer is idle')
    status = printer(IDLE_QUERY)['status']
    message = 'Wait until Klipper is Ready and the printer is idle'
    if status['print_stats']['state'] not in ('standby', 'complete', 'cancelled', 'error'):
        raise ValueError(message)
    control = status.get('m300_print_control') or {}
    if (status['pause_resume']['is_paused'] is not False or control.get('paused')
            or status['idle_timeout']['state'] not in ('Idle', 'Ready')):
        raise ValueError(message + ' (paused or moving)')
    for name in ('m300_print_control', *BUSY_OBJECTS):
        if (status.get(name) or {}).get('busy'):
            raise ValueError(message + f' ({name} is busy)')
    toolhead = status['toolhead']
    clocks = (toolhead['print_time'], toolhead['estimated_print_time'])
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in clocks):
        raise ValueError(message + ' (motion clocks are unavailable)')
    if clocks[0] > clocks[1]:
        raise ValueError(message + ' (motion is still queued)')
    if status['extruder']['target'] != 0 or status['heater_bed']['target'] != 0:
        raise ValueError(message + ' (turn off both heater targets)')
    return info


def nginx_sites(config):
    lexer = shlex.shlex(config, posix=True, punctuation_chars='{};')
    lexer.whitespace_split = True
    stack, words, sites = [], [], []
    for item in lexer:
        for token in item if set(item) <= set('{};') else (item,):
            if token == '{':
                site = stack[-1][1] if stack else None
                if words == ['server']:
                    site = {'ports': set(), 'roots': set()}
                    sites.append(site)
                stack.append((words, site))
            elif token == '}':
                stack.pop()
            elif token == ';':
                if stack and words:
                    block, site = stack[-1]
                    if site is not None and block == ['server'] and words[0] == 'listen':
                        site['ports'].add(words[1].rsplit(':', 1)[-1])
                    serves_index = (block == ['server'] or
                                    block in (['location', '/'], ['location', '=', '/'],
                                              ['location', '=', '/index.html'],
                                              ['location', '^~', '/']))
                    if site is not None and serves_index and words[0] in ('root', 'alias'):
                        site['roots'].add(words[1])
            else:
                words.append(token)
                continue
            words = []
    return sites


def nginx_root(config, port):
    sites = nginx_sites(config)
    matching = [site for site in sites if str(port) in site['ports']]
    roots = set().union(*(site['roots'] for site in matching))
    if len(roots) != 1 or any(not site['roots'] for site in matching):
        raise ValueError(f'Could not identify one Fluidd web root on nginx port {port}; use --fluidd-root')
    root = roots.pop()
    if '$' in root or not Path(root).is_absolute():
        raise ValueError('Fluidd web root must be an absolute directory; use --fluidd-root')
    return Path(root)


def verified_web_root(path):
    root = path.resolve(strict=True)
    index = (root / 'index.html').read_text(encoding='utf-8').lower()
    if '<title>fluidd</title>' not in index or len(root.parts) < 3 or (root / '.git').exists():
        raise ValueError(f'Expected a dedicated Fluidd web directory at {root}')
    return root



def valid_port(value):
    """An explicit/saved port is never silently changed to another endpoint."""
    if isinstance(value, bool):
        raise ValueError('Fluidd port must be an integer from 1 to 65535')
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Fluidd port must be an integer from 1 to 65535') from exc
    if str(port) != str(value) or not 1 <= port <= 65535:
        raise ValueError('Fluidd port must be an integer from 1 to 65535')
    return port


def load_install_state(config_dir):
    """Read a local receipt, outside the checksum-protected Git package."""
    path = Path(config_dir) / INSTALL_STATE_NAME
    if not path.exists():
        return None
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError('Invalid installer state file')
        state = json.loads(path.read_text())
        if (state.get('schema') != 1 or not isinstance(state.get('fluidd_root'), str)
                or not Path(state['fluidd_root']).is_absolute()):
            raise ValueError('Invalid installer state fields')
        state['fluidd_port'] = valid_port(state['fluidd_port'])
        return state
    except (ValueError, KeyError, AttributeError, OSError) as exc:
        raise ValueError('Invalid saved Fluidd selection; use --port or --fluidd-root '
                         'to select the real endpoint again') from exc


def select_fluidd(config, port=None, root=None, saved=None):
    """Explicit arguments > revalidated receipt > 4480 > one unique Fluidd.

    Never edit nginx, migrate ports, trust an unverified remembered directory,
    or guess when two installations are present. Legacy 4080/80 installations
    are accepted only if identification is unambiguous or explicitly requested.
    """
    if port is not None:
        port = valid_port(port)
        candidate = verified_web_root(root or nginx_root(config, port))
        return candidate, port, 'explicit'
    if root is not None:
        candidate = verified_web_root(root)
        matches = []
        for site in nginx_sites(config):
            for value in site['ports']:
                try:
                    number = valid_port(value)
                    if verified_web_root(nginx_root(config, number)) == candidate:
                        matches.append(number)
                except (ValueError, OSError):
                    continue
        matches = set(matches)
        if DEFAULT_FLUIDD_PORT in matches:
            return candidate, DEFAULT_FLUIDD_PORT, 'explicit-root'
        if len(matches) == 1:
            return candidate, matches.pop(), 'explicit-root'
        raise ValueError('Supply --port with --fluidd-root when nginx does not '
                         'identify exactly one listen port for this directory')
    if saved is not None:
        number = valid_port(saved['fluidd_port'])
        try:
            candidate = verified_web_root(nginx_root(config, number))
            if str(candidate) != saved['fluidd_root']:
                raise ValueError('Saved web root changed')
        except (ValueError, OSError) as exc:
            raise ValueError('Saved Fluidd endpoint no longer matches nginx; '
                             'use --port or --fluidd-root to select it explicitly') from exc
        return candidate, number, 'saved-revalidated'
    sites = nginx_sites(config)
    if any(str(DEFAULT_FLUIDD_PORT) in site['ports'] for site in sites):
        # Ambiguity at the preferred port is an error, not a reason to silently
        # update an unrelated second server on a different port.
        return (verified_web_root(nginx_root(config, DEFAULT_FLUIDD_PORT)),
                DEFAULT_FLUIDD_PORT, 'default-4480')
    candidates = set()
    for value in set().union(*(site['ports'] for site in sites)):
        try:
            number = valid_port(value)
            candidate = verified_web_root(nginx_root(config, number))
            candidates.add((candidate, number))
        except (ValueError, OSError):
            continue
    if len(candidates) != 1:
        raise ValueError('Could not identify exactly one Fluidd installation '
                         '(preferred port 4480); use --port or --fluidd-root')
    candidate, number = candidates.pop()
    return candidate, number, 'unique-nginx-detection'


def save_install_state(config_dir, root, port):
    """Commit a receipt only AFTER successful host and web deployment."""
    target = Path(config_dir) / INSTALL_STATE_NAME
    state = dict(schema=1, fluidd_port=valid_port(port),
                 fluidd_root=str(verified_web_root(root)))
    fd, name = tempfile.mkstemp(prefix='.m300-installer-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)
    return target

def deploy_web(source, root, build_id, *, execute=run):
    marker = root / '.m300-fluidd-build'
    if marker.is_file() and marker.read_text().strip() == build_id:
        return None
    stage = Path(execute('sudo', 'mktemp', '-d', '--tmpdir=' + str(root.parent),
                         '.m300-fluidd.XXXXXX', capture=True).strip())
    backup = stage.with_name(stage.name + '.previous')
    try:
        execute('sudo', 'cp', '-a', '--', str(source) + '/.', stage)
        config = root / 'config.json'
        if config.is_file():
            execute('sudo', 'cp', '-pL', '--', config, stage / config.name)
        execute('sudo', 'chmod', '--reference=' + str(root), stage)
        execute('sudo', 'chown', '--reference=' + str(root), stage)
        execute('sudo', 'mv', '-T', '--', root, backup)
        try:
            execute('sudo', 'mv', '-T', '--', stage, root)
            execute('sudo', 'systemctl', 'reload', 'nginx')
        except (subprocess.CalledProcessError, KeyboardInterrupt):
            if not stage.exists():
                execute('sudo', 'mv', '-T', '--', root, stage)
            execute('sudo', 'mv', '-T', '--', backup, root)
            raise
    finally:
        execute('sudo', 'rm', '-rf', '--', stage)
    return backup


def restore_web(root, backup, *, execute=run):
    if backup is None:
        return
    replaced = backup.with_suffix('')
    execute('sudo', 'mv', '-T', '--', root, replaced)
    try:
        execute('sudo', 'mv', '-T', '--', backup, root)
    except BaseException:
        execute('sudo', 'mv', '-T', '--', replaced, root)
        raise
    execute('sudo', 'rm', '-rf', '--', replaced)
    execute('sudo', 'systemctl', 'reload', 'nginx')


def restore_host(host, args, receipt, *, restart_moonraker=False):
    if receipt is None:
        return
    run('sudo', 'systemctl', 'stop', 'klipper.service')
    try:
        run(sys.executable, 'install.py', *args, '--rollback', receipt, cwd=host)
    finally:
        run('sudo', 'systemctl', 'start', 'klipper.service')
        if restart_moonraker:
            run('sudo', 'systemctl', 'restart', 'moonraker.service')


def apply_host(host, args, plan, *, repair_startup=False):
    if plan['status'] == 'ALREADY_M300_HOST':
        if repair_startup:
            raise ValueError('Startup repair found no host files to replace')
        wait_ready()
        return
    if plan['status'] != 'PLAN_M300_HOST':
        raise ValueError('Unexpected host install plan')
    require_idle(repair_startup=repair_startup)
    restart_moonraker = any(Path(p).name == 'moonraker.conf' for p in plan.get('files', ()))
    run('sudo', 'systemctl', 'stop', 'klipper.service')
    try:
        applied = json.loads(run(sys.executable, 'install.py', *args, '--apply', cwd=host, capture=True))
        receipt = applied.get('receipt')
        if applied['status'] != 'ALREADY_M300_HOST' and not receipt:
            raise ValueError('Host installer returned no backup receipt')
    except BaseException:
        run('sudo', 'systemctl', 'start', 'klipper.service')
        raise
    try:
        run('sudo', 'systemctl', 'start', 'klipper.service')
        if restart_moonraker:
            run('sudo', 'systemctl', 'restart', 'moonraker.service')
        # The exact legacy startup repair may still require the operator to
        # clear a latched MCU fault, so only normal updates wait for Ready.
        if not repair_startup:
            wait_ready()
    except BaseException as exc:
        try:
            restore_host(host, args, receipt, restart_moonraker=restart_moonraker)
        except (ValueError, OSError, subprocess.CalledProcessError) as restore_error:
            raise ValueError(f'{exc}; host rollback failed using {receipt}: {restore_error}') from exc
        raise
    return receipt


def wait_ready():
    deadline = time.monotonic() + 45
    reason = ''
    while time.monotonic() < deadline:
        try:
            info = printer('/printer/info')
            if info['state'] == 'ready':
                return
            reason = info.get('state_message') or info['state']
        except (URLError, TimeoutError) as exc:
            reason = str(exc)
        time.sleep(1)
    raise ValueError(f'Klipper did not reach Ready after the host update: {reason}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=valid_port, default=None,
                        help='Existing Fluidd port (saved selection, then 4480, then unique nginx detection)')
    parser.add_argument('--fluidd-root', type=Path, help='Override nginx web root detection')
    parser.add_argument('--organize-config', action='store_true',
                        help='Organize current configuration, retaining hardware values and saved PID')
    parser.add_argument('--qualified-first-print-z', action='store_true',
                        help='Explicitly apply the mechanically qualified 2026-11-11 M300 Z profile')
    parser.add_argument('--repair-startup',action='store_true',
                        help='Repair the verified R29 early-status crash while Shutdown; no MCU reset')
    args = parser.parse_args()
    if not (PACKAGE / 'SHA256SUMS').is_file():
        parser.exit(1, 'Run this installer from the extracted GitHub Actions artifact.\n')
    if os.geteuid() == 0:
        parser.exit(1, 'Run as the Klipper account on the Orange Pi.\n')
    try:
        run('sha256sum', '-c', '--quiet', 'SHA256SUMS', cwd=PACKAGE)
        info = require_idle(repair_startup=args.repair_startup)
        host = PACKAGE / 'M300_HOST'
        host_args = ('--root', info['klipper_path'], '--config', info['config_file'])
        if args.organize_config:
            host_args += ('--organize-config',)
        if args.qualified_first_print_z:
            host_args += ('--qualified-first-print-z',)
        plan = json.loads(run(sys.executable, 'install.py', *host_args, cwd=host, capture=True))
        run('sudo', '-v')
        if args.repair_startup:
            # Repair the host before requiring Ready or deploying the web UI.
            # Hardware/MCU latches still require the operator's explicit reset.
            host_receipt = apply_host(host,host_args,plan,repair_startup=True)
            print(json.dumps(dict(status='REPAIRED_M300_SERVICE_STARTUP',
                next_command='FIRMWARE_RESTART',mcu_flashed=False,mcu_reset=False,
                host_update=plan['host_update'],host_receipt=host_receipt)))
            return
        config = run('sudo', 'nginx', '-T', capture=True)
        config_dir = Path(info['config_file']).parent
        saved = load_install_state(config_dir) if args.port is None and args.fluidd_root is None else None
        root, fluidd_port, selection = select_fluidd(config, args.port, args.fluidd_root, saved)
        print(json.dumps(dict(status='FLUIDD_ENDPOINT_SELECTED', fluidd_port=fluidd_port,
                              fluidd_root=str(root), source=selection)))
        archive = PACKAGE / 'M300_FLUIDD.zip'
        build_id = hashlib.sha256(archive.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='m300-fluidd-') as temp:
            with ZipFile(archive) as bundle:
                bundle.extractall(temp)
            source = verified_web_root(Path(temp) / 'fluidd-m300')
            (source / '.m300-fluidd-build').write_text(build_id + '\n')
            host_receipt = apply_host(host, host_args, plan)
            run(sys.executable, 'setup_fluidd.py', '--apply', '--config-directory',
                Path(info['config_file']).parent, cwd=host)
            backup = deploy_web(source, root, build_id)
        receipt = save_install_state(config_dir, root, fluidd_port)
        print(json.dumps({'status': 'INSTALLED_M300_HOST', 'fluidd_root': str(root),
                          'host_update': plan['host_update'], 'host_receipt': host_receipt,
                          'fluidd_port': fluidd_port, 'selection': selection,
                          'install_state': str(receipt),
                          'fluidd_backup': str(backup) if backup else None, 'mcu_flashed': False}))
    except (ValueError, OSError, KeyError, IndexError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'M300 installation stopped: {exc}\n')


if __name__ == '__main__':
    main()
