#!/usr/bin/env python3
"""Update M300 Classic Klipper, with a separate opt-in Fluidd web update."""
import argparse
from contextlib import closing
import hashlib
from http.client import HTTPConnection, HTTPException
import json
import math
import os
from pathlib import Path
import re
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
LEGACY_WEB_MARKER = '.m300-fluidd-build'
HTML_CONTENT_TYPES = ('text/html',)
JS_CONTENT_TYPES = ('application/javascript', 'text/javascript', 'application/x-javascript')
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


def verified_web_root(path, *, repair_source=None):
    root = path.resolve(strict=True)
    if len(root.parts) >= 3 and not (root / '.git').exists():
        index = root / 'index.html'
        if '<title>fluidd</title>' in index.read_text(encoding='utf-8').lower():
            return root
        if recoverable_web_files(root, repair_source):
            return root
    raise ValueError(f'Expected a dedicated Fluidd web directory at {root}')



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


def select_fluidd(config, port=None, root=None, saved=None, *, repair_source=None):
    """Explicit arguments > revalidated receipt > 4480 > one unique Fluidd.

    Never edit nginx, migrate ports, trust an unverified remembered directory,
    or guess when two installations are present. Legacy 4080/80 installations
    are accepted only if identification is unambiguous or explicitly requested.
    """
    def verify(path):
        return verified_web_root(path, repair_source=repair_source)

    if port is not None:
        port = valid_port(port)
        candidate = verify(root or nginx_root(config, port))
        return candidate, port, 'explicit'
    if root is not None:
        candidate = verify(root)
        matches = []
        for site in nginx_sites(config):
            for value in site['ports']:
                try:
                    number = valid_port(value)
                    if verify(nginx_root(config, number)) == candidate:
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
            candidate = verify(nginx_root(config, number))
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
        return (verify(nginx_root(config, DEFAULT_FLUIDD_PORT)),
                DEFAULT_FLUIDD_PORT, 'default-4480')
    candidates = set()
    for value in set().union(*(site['ports'] for site in sites)):
        try:
            number = valid_port(value)
            candidate = verify(nginx_root(config, number))
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

def extract_web(archive, destination):
    with ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('Unsafe Fluidd archive member')
        bundle.extractall(destination)
    source = verified_web_root(destination / 'fluidd-m300')
    for path in source.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)
    return source


def same_web_contents(source, root, *, http_verified):
    ignored = {Path(LEGACY_WEB_MARKER)}
    if (root / 'config.json').is_file():
        ignored.add(Path('config.json'))

    def paths(directory):
        return {path.relative_to(directory): path for path in directory.rglob('*')
                if path.relative_to(directory) not in ignored}

    try:
        new, old = paths(source), paths(root)
        if new.keys() != old.keys():
            return False
        for name, incoming in new.items():
            existing = old[name]
            required = 0o005 if incoming.is_dir() else 0o004
            if (existing.is_symlink() or incoming.is_dir() != existing.is_dir()
                    or (not http_verified and existing.stat().st_mode & required != required)):
                return False
            if incoming.is_file() and (not existing.is_file()
                                       or incoming.read_bytes() != existing.read_bytes()):
                return False
    except OSError:
        return False
    return True


def web_probe_files(root):
    index = (root / 'index.html').read_bytes()
    asset = re.search(rb'\bsrc=["\'](?:\./|/)?(assets/[\w.-]+-[\w-]+\.js)["\']', index)
    if asset:
        name = asset[1].decode('ascii')
        return (('/', index, HTML_CONTENT_TYPES),
                ('/' + name, (root / name).read_bytes(), JS_CONTENT_TYPES))
    return ()


def recoverable_web_files(root, source):
    index = root / 'index.html'
    if (source is None or index.is_symlink() or not index.is_file()
            or index.stat().st_size != 0):
        return ()
    try:
        files = web_probe_files(source)
        if not files:
            return ()
        script, data, _ = files[1]
        manifest = 'manifest.webmanifest'
        for name, data in ((script.lstrip('/'), data), (manifest, (source / manifest).read_bytes())):
            existing = root / name
            if (existing.resolve() != existing or not existing.is_file()
                    or existing.read_bytes() != data):
                return ()
    except OSError:
        return ()
    return (('/', b'', HTML_CONTENT_TYPES), files[1])


def web_responds(host, port, files):
    try:
        with closing(HTTPConnection(host, port, timeout=2)) as connection:
            for path, expected, content_types in files:
                connection.request('GET', f'{path}?m300_probe={time.monotonic_ns()}',
                                   headers={'Cache-Control': 'no-cache'})
                with connection.getresponse() as response:
                    if (response.status != 200 or response.headers.get_content_type() not in content_types
                            or response.read(len(expected) + 1) != expected):
                        return False
    except (OSError, HTTPException):
        return False
    return bool(files)


def local_web_host(root, port, *, repair_source=None):
    if port is None:
        return None
    try:
        files = web_probe_files(root) or recoverable_web_files(root, repair_source)
    except OSError:
        return None
    return next((host for host in ('127.0.0.1', '::1') if web_responds(host, port, files)), None)


def deploy_web(source, root, *, port=None, execute=run):
    local_host = local_web_host(root, port, repair_source=source)
    if same_web_contents(source, root, http_verified=local_host is not None):
        return None
    expected = web_probe_files(source) if local_host is not None else ()
    if local_host is not None and not expected:
        raise ValueError('Missing a hashed Fluidd JavaScript entrypoint in the package')
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
        reloaded = False
        try:
            execute('sudo', 'mv', '-T', '--', stage, root)
            execute('sudo', 'systemctl', 'reload', 'nginx')
            reloaded = True
            if local_host is not None:
                for _ in range(3):
                    if web_responds(local_host, port, expected):
                        break
                    time.sleep(.2)
                else:
                    raise ValueError(f'Fluidd did not serve the deployed page and JavaScript on port {port}')
        except BaseException:
            if not stage.exists():
                execute('sudo', 'mv', '-T', '--', root, stage)
            execute('sudo', 'mv', '-T', '--', backup, root)
            if reloaded:
                execute('sudo', 'systemctl', 'reload', 'nginx')
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


def update_fluidd(args):
    run('sudo', '-v')
    config = run('sudo', 'nginx', '-T', capture=True)
    saved = None
    if args.port is None and args.fluidd_root is None:
        try:
            config_file = printer('/printer/info')['config_file']
        except (OSError, ValueError, KeyError):
            pass
        else:
            saved = load_install_state(Path(config_file).parent)
    with tempfile.TemporaryDirectory(prefix='m300-fluidd-') as temp:
        source = extract_web(PACKAGE / 'M300_FLUIDD.zip', Path(temp))
        root, port, selection = select_fluidd(
            config, args.port, args.fluidd_root, saved, repair_source=source)
        print(json.dumps(dict(status='FLUIDD_ENDPOINT_SELECTED', fluidd_port=port,
                              fluidd_root=str(root), source=selection)))
        backup = deploy_web(source, root, port=port)
    print(json.dumps(dict(status='INSTALLED_M300_FLUIDD', fluidd_root=str(root),
                          fluidd_port=port, selection=selection,
                          fluidd_backup=str(backup) if backup else None, mcu_flashed=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-fluidd', action='store_true',
                        help='Update the Fluidd web files only; leave Klipper and Moonraker alone')
    parser.add_argument('--port', type=valid_port, default=None,
                        help='With --update-fluidd, select the existing Fluidd port (default 4480)')
    parser.add_argument('--fluidd-root', type=Path, help='Override web root detection with --update-fluidd')
    parser.add_argument('--organize-config', action='store_true',
                        help='Organize current configuration, retaining hardware values and saved PID')
    parser.add_argument('--qualified-first-print-z', action='store_true',
                        help='Explicitly apply the mechanically qualified 2026-11-11 M300 Z profile')
    parser.add_argument('--repair-startup',action='store_true',
                        help='Repair the verified R29 early-status crash while Shutdown; no MCU reset')
    args = parser.parse_args()
    if args.update_fluidd and (args.organize_config or args.qualified_first_print_z or args.repair_startup):
        parser.error('--update-fluidd is a separate operation from Klipper host options')
    if not (PACKAGE / 'SHA256SUMS').is_file():
        parser.exit(1, 'Run this installer from the extracted GitHub Actions artifact.\n')
    if os.geteuid() == 0:
        parser.exit(1, 'Run as the Klipper account on the Orange Pi.\n')
    try:
        run('sha256sum', '-c', '--quiet', 'SHA256SUMS', cwd=PACKAGE)
        if args.update_fluidd:
            update_fluidd(args)
            return
        info = require_idle(repair_startup=args.repair_startup)
        host = PACKAGE / 'M300_HOST'
        host_args = ('--root', info['klipper_path'], '--config', info['config_file'])
        if args.organize_config:
            host_args += ('--organize-config',)
        if args.qualified_first_print_z:
            host_args += ('--qualified-first-print-z',)
        plan = json.loads(run(sys.executable, 'install.py', *host_args, cwd=host, capture=True))
        run('sudo', '-v')
        host_receipt = apply_host(host, host_args, plan, repair_startup=args.repair_startup)
        if args.repair_startup:
            print(json.dumps(dict(status='REPAIRED_M300_SERVICE_STARTUP',
                next_command='FIRMWARE_RESTART',mcu_flashed=False,mcu_reset=False,
                host_update=plan['host_update'],host_receipt=host_receipt)))
            return
        print(json.dumps(dict(status='INSTALLED_M300_HOST', host_update=plan['host_update'],
                              host_receipt=host_receipt, mcu_flashed=False)))
    except (ValueError, OSError, KeyError, IndexError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'M300 installation stopped: {exc}\n')


if __name__ == '__main__':
    main()
