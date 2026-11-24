#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# install_camera.py - Opcjonalna kamera USB M300: konfiguracja, usługa i podgląd Fluidd.
"""Optional USB camera for M300 / Debian and Armbian. Default: read-only plan.

--enable --apply installs ustreamer, selects a USB camera and registers it in
Fluidd through Moonraker. Later edit printer_data/config/m300_camera.conf and
run --apply. False stops/disables the streaming service as well as the view.
Klipper, its configuration and MCU are never restarted or modified.
"""
import argparse
import configparser
import datetime
import json
import math
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
NAME = 'M300 USB'
ROUTE = '/m300-camera/'
UNIT = Path('/etc/systemd/system/m300-camera.service')
OWNER = '# Managed by M300 optional USB camera installer.'
BEGIN = '    # BEGIN M300 CAMERA\n'
END = '    # END M300 CAMERA\n'


def run(*args):
    return subprocess.run([str(a) for a in args], check=True, text=True,
                          stdout=subprocess.PIPE).stdout


def template():
    for path in (HERE/'FIRST_INSTALL/m300_camera.conf',
                 HERE.parent/'host/config/m300_camera.conf'):
        if path.is_file():
            return path.read_text()
    raise ValueError('Missing camera configuration template')


def configuration(text):
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#', ';'))
    parser.read_string(text)
    if parser.sections() != ['camera'] or parser.defaults():
        raise ValueError('Expected one [camera] section')
    section = parser['camera']
    fields = {'enabled', 'device', 'resolution', 'fps', 'format', 'port', 'fluidd_port'}
    if set(section) != fields:
        raise ValueError('Camera fields must be: '+', '.join(sorted(fields)))
    value = dict(section)
    value['enabled'] = section.getboolean('enabled')
    for key in ('fps', 'port', 'fluidd_port'):
        value[key] = section.getint(key)
    if not 1 <= value['fps'] <= 60:
        raise ValueError('fps must be between 1 and 60')
    if not 1024 <= value['port'] <= 65535 or not 1 <= value['fluidd_port'] <= 65535:
        raise ValueError('Camera port must be 1024..65535; Fluidd port must be 1..65535')
    if value['port'] in (value['fluidd_port'], 7125):
        raise ValueError('Camera port must differ from Fluidd and Moonraker')
    size = re.fullmatch(r'([0-9]+)x([0-9]+)', value['resolution'])
    if not size or not all(16 <= int(v) <= 8192 for v in size.groups()):
        raise ValueError('Invalid resolution, e.g. 640x480')
    if value['format'] not in ('auto', 'MJPEG', 'YUYV'):
        raise ValueError('format must be auto, MJPEG or YUYV')
    device = value['device']
    if device != 'auto' and not re.fullmatch(r'/dev/(?:video[0-9]+|v4l/by-(?:id|path)/[^/\s]+)', device):
        raise ValueError('Use auto or a /dev/videoN or /dev/v4l/by-id/by-path device')
    return value


def updated_config(text, values):
    for key in ('enabled', 'device'):
        text = re.sub(r'(?m)^'+key+r'\s*[:=].*$', key+': '+str(values[key]), text)
    return text


def choose_device(requested):
    paths = [Path(requested)] if requested != 'auto' else (
        sorted(Path('/dev/v4l/by-id').glob('*-video-index0')) +
        sorted(Path('/dev/v4l/by-path').glob('*usb*-video-index0')) +
        sorted(Path('/dev').glob('video[0-9]*')))
    devices = {}
    for path in paths:
        real = path.resolve()
        if not path.is_char_device() or not re.fullmatch(r'/dev/video[0-9]+', str(real)):
            continue
        # Ignore SoC encoders/decoders and metadata nodes.
        if requested == 'auto' and 'usb' not in str((Path('/sys/class/video4linux')/real.name/'device').resolve()):
            continue
        try:
            info = run('v4l2-ctl', '--device='+str(path), '--all')
        except subprocess.CalledProcessError:
            continue
        # A metadata node can advertise the parent device's Video Capture
        # capability. Its own Device Caps are authoritative when present.
        caps = re.split(r'\bDevice Caps\s*:', info, maxsplit=1)[-1]
        if re.search(r'(?m)^\s*Video Capture(?: Multiplanar)?\s*$', caps):
            devices.setdefault(str(real), str(path))
    if len(devices) != 1:
        raise ValueError('Expected one USB capture camera; found '+str(list(devices.values()))+
                         '. Connect the camera or pass --device /dev/v4l/by-id/...-video-index0')
    return next(iter(devices.values()))


def capture_format(device, requested):
    formats = run('v4l2-ctl', '--device='+device, '--list-formats-ext')
    available = re.findall(r"'([A-Z0-9]+)'", formats)
    selected = ('MJPEG' if 'MJPG' in available else 'YUYV') if requested == 'auto' else requested
    if ('MJPG' if selected == 'MJPEG' else selected) not in available:
        raise ValueError('Camera does not support '+selected+'; see v4l2-ctl --list-formats-ext')
    return selected


def server_blocks(text):
    """Locate real server blocks without interpreting comments or quoted braces."""
    tokens = re.finditer(r'''\#.*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\$\{[^}]*\}|[{};]|[^\s{};\#]+''', text)
    stack, words, result = [], [], []
    for token in tokens:
        word = token.group()
        if word.startswith('#'):
            continue
        if word == '{':
            stack.append({'header': words, 'open': token.start(), 'ports': set()})
            words = []
        elif word == '}':
            if not stack:
                raise ValueError('Unbalanced nginx configuration')
            block = stack.pop()
            if block['header'] == ['server']:
                result.append(dict(start=block['open'], end=token.start(), ports=block['ports']))
            words = []
        elif word == ';':
            if stack and stack[-1]['header'] == ['server'] and words[:1] == ['listen']:
                stack[-1]['ports'].add(words[1].strip('"\'').rsplit(':', 1)[-1])
            words = []
        else:
            words.append(word)
    if stack:
        raise ValueError('Unbalanced nginx configuration')
    return result


def nginx_route(text, port, backend):
    blocks = [b for b in server_blocks(text) if str(port) in b['ports']]
    if len(blocks) != 1:
        raise ValueError('Expected one nginx server block for Fluidd port '+str(port))
    block = blocks[0]
    body = text[block['start']+1:block['end']]
    managed = re.compile(re.escape(BEGIN)+r'.*?'+re.escape(END), re.S)
    if body.count(BEGIN) != body.count(END) or body.count(BEGIN) > 1:
        raise ValueError('Invalid managed camera nginx block')
    body = managed.sub('', body)
    if ROUTE in body:
        raise ValueError('An unmanaged '+ROUTE+' route already exists')
    proxy = (BEGIN+'    location ^~ '+ROUTE+' {\n'
             '        proxy_pass http://127.0.0.1:'+str(backend)+'/;\n'
             '        proxy_http_version 1.1;\n'
             '        proxy_set_header Connection "";\n'
             '        proxy_buffering off;\n'
             '        proxy_request_buffering off;\n'
             '        proxy_read_timeout 60s;\n'
             '    }\n'+END)
    return text[:block['start']+1]+body.rstrip()+'\n'+proxy+text[block['end']:]


def nginx_site(dump, port, explicit=None):
    pieces = re.split(r'(?m)^# configuration file ([^\n]+):\n', dump)
    matches = set()
    for index in range(1, len(pieces), 2):
        path = Path(pieces[index]).resolve()
        if explicit is not None and path != explicit.resolve():
            continue
        if any(str(port) in b['ports'] for b in server_blocks(pieces[index+1])):
            matches.add(path)
    if len(matches) != 1:
        raise ValueError('Could not select one active nginx site on port '+str(port)+
                         '; use --nginx-site with its /etc/nginx path')
    path = matches.pop()
    if not path.is_relative_to('/etc/nginx') or not path.is_file():
        raise ValueError('Expected an active site under /etc/nginx')
    return path


def service(value, executable, pixel_format, username):
    def quote(word):
        return '"'+str(word).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '$$')+'"'
    command = [executable, '--device='+value['device'], '--host=127.0.0.1',
               '--port='+str(value['port']), '--resolution='+value['resolution'],
               '--desired-fps='+str(value['fps']), '--format='+pixel_format,
               '--encoder='+('HW' if pixel_format == 'MJPEG' else 'CPU'),
               '--workers=1', '--slowdown']
    return (OWNER+'\n[Unit]\nDescription=M300 optional USB camera\nAfter=network.target\n\n'
            '[Service]\nType=simple\nUser='+username+'\nSupplementaryGroups=video\n'
            'ExecStart='+' '.join(quote(v) for v in command)+'\nRestart=on-failure\nRestartSec=5\n'
            'Nice=10\nCPUWeight=20\nNoNewPrivileges=true\nProtectSystem=strict\n'
            'ProtectHome=true\nPrivateTmp=true\n\n[Install]\nWantedBy=multi-user.target\n')


def moonraker(endpoint, payload=None, method=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request('http://127.0.0.1:7125'+endpoint, data=data,
                      headers={'Content-Type': 'application/json'}, method=method)
    with urlopen(request, timeout=5) as response:
        return json.load(response)['result']


def existing_webcam(cameras):
    found = [c for c in cameras if c['name'] == NAME]
    if len(found) > 1 or (found and (found[0]['source'] != 'database'
                                  or found[0]['stream_url'] != ROUTE+'stream')):
        raise ValueError('An unmanaged '+NAME+' webcam already exists; rename it in Fluidd first')
    return found[0] if found else None


def webcam_payload(value, old=None):
    width, height = map(int, value['resolution'].split('x'))
    divisor = math.gcd(width, height)
    # Native MJPEG display works in OrcaSlicer's embedded browser. Preserve
    # the user's selected display service when applying capture settings again.
    display_service = (old or {}).get('service') or 'uv4l-mjpeg'
    payload = dict(name=NAME, enabled=value['enabled'], service=display_service,
                   stream_url=ROUTE+'stream', snapshot_url=ROUTE+'snapshot',
                   target_fps=value['fps'], target_fps_idle=min(5, value['fps']),
                   aspect_ratio=str(width//divisor)+':'+str(height//divisor))
    if old:
        payload['uid'] = old['uid']
    return payload


def privileged_write(path, text):
    with tempfile.NamedTemporaryFile(mode='w', prefix='m300-camera-') as source:
        source.write(text)
        source.flush()
        run('sudo', 'install', '-o', 'root', '-g', 'root', '-m', '644', source.name, path)


def save_config(path, text):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.m300-camera-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o644)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def is_state(action):
    return subprocess.run(['systemctl', action, UNIT.name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


def verify_video(value):
    """Check actual capture, then the proxy on the user's Fluidd port."""
    deadline = time.monotonic()+15
    error = 'no live frames'
    while time.monotonic() < deadline:
        try:
            with urlopen('http://127.0.0.1:'+str(value['port'])+'/state', timeout=2) as response:
                state = json.load(response)['result']
            if state['source']['online'] is not True:
                raise ValueError('Camera capture is offline')
            base = 'http://127.0.0.1:'+str(value['fluidd_port'])+ROUTE
            with urlopen(base+'state', timeout=2) as response:
                if json.load(response)['result']['source']['online'] is not True:
                    raise ValueError('Fluidd camera proxy has no live video')
            with urlopen(base+'snapshot', timeout=3) as response:
                if response.headers.get_content_type() != 'image/jpeg' or response.read(2) != b'\xff\xd8':
                    raise ValueError('Camera snapshot is not JPEG')
            with urlopen(base+'stream', timeout=3) as response:
                if (response.headers.get_content_type() != 'multipart/x-mixed-replace'
                        or b'image/jpeg' not in response.read(256).lower()):
                    raise ValueError('Camera stream is not multipart MJPEG')
            return
        except (URLError, OSError, ValueError, KeyError) as exc:
            error = str(exc)
            time.sleep(0.5)
    raise ValueError('Camera verification failed: '+error+'; see journalctl -u '+UNIT.name)


def apply(value, config_path, text, nginx_path=None):
    if UNIT.is_symlink() or (UNIT.exists() and not UNIT.read_text().startswith(OWNER+'\n')):
        raise ValueError('Refusing to replace an unmanaged '+str(UNIT))
    if not value['enabled']:
        # No camera, nginx, dependencies or running Moonraker are needed to stop video.
        if UNIT.exists():
            run('sudo', 'systemctl', 'disable', '--now', UNIT.name)
        save_config(config_path, updated_config(text, value))
        try:
            old = existing_webcam(moonraker('/server/webcams/list')['webcams'])
            if old:
                moonraker('/server/webcams/item', {'uid': old['uid'], 'enabled': False})
        except (URLError, OSError, ValueError, KeyError) as exc:
            print('Video stopped; Fluidd view could not be synchronized: '+str(exc), file=sys.stderr)
        return dict(status='CAMERA_DISABLED', config=str(config_path), video_verified=False)

    old = existing_webcam(moonraker('/server/webcams/list')['webcams'])
    site = nginx_site(run('sudo', 'nginx', '-T'), value['fluidd_port'], nginx_path)
    previous_site = site.read_text()
    new_site = nginx_route(previous_site, value['fluidd_port'], value['port'])
    # Use the distro binary; ProtectHome intentionally hides personal trees.
    executable = Path('/usr/bin/ustreamer')
    if not executable.is_file() or not shutil.which('v4l2-ctl'):
        run('sudo', 'apt-get', 'update')
        run('sudo', 'apt-get', 'install', '-y', '--no-install-recommends', 'ustreamer', 'v4l-utils')
    value['device'] = choose_device(value['device'])
    pixel_format = capture_format(value['device'], value['format'])
    active, enabled = is_state('is-active'), is_state('is-enabled')
    previous_unit = UNIT.read_text() if UNIT.exists() else None
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', value['port']))
        except OSError:
            if not active or not previous_unit or '--port='+str(value['port'])+'"' not in previous_unit:
                raise ValueError('Camera port is already occupied; change port in '+str(config_path))
    backup = config_path.parent/('m300-camera-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir()
    (backup/'nginx.conf').write_text(previous_site)
    (backup/'receipt.json').write_text(json.dumps(dict(nginx=str(site), unit=str(UNIT),
        previously_active=active, previously_enabled=enabled, webcam=old), indent=2)+'\n')
    if previous_unit:
        (backup/UNIT.name).write_text(previous_unit)
    if config_path.exists():
        shutil.copy2(config_path, backup/config_path.name)
    webcam_attempted = False
    try:
        privileged_write(UNIT, service(value, executable, pixel_format,
                                       pwd.getpwuid(os.geteuid()).pw_name))
        privileged_write(site, new_site)
        run('sudo', 'nginx', '-t')
        run('sudo', 'systemctl', 'daemon-reload')
        run('sudo', 'systemctl', 'enable', UNIT.name)
        run('sudo', 'systemctl', 'restart', UNIT.name)
        run('sudo', 'systemctl', 'reload', 'nginx')
        verify_video(value)
        save_config(config_path, updated_config(text, value))
        webcam_attempted = True
        moonraker('/server/webcams/item', webcam_payload(value, old))
    except Exception:
        # Restore only the files and service state changed by this operation.
        privileged_write(site, previous_site)
        run('sudo', 'systemctl', 'disable', '--now', UNIT.name)
        if previous_unit:
            privileged_write(UNIT, previous_unit)
        else:
            run('sudo', 'rm', '--', UNIT)
        run('sudo', 'systemctl', 'daemon-reload')
        if enabled:
            run('sudo', 'systemctl', 'enable', UNIT.name)
        if active:
            run('sudo', 'systemctl', 'start', UNIT.name)
        run('sudo', 'nginx', '-t')
        run('sudo', 'systemctl', 'reload', 'nginx')
        if (backup/config_path.name).exists():
            shutil.copy2(backup/config_path.name, config_path)
        else:
            config_path.unlink(missing_ok=True)
        if webcam_attempted:
            try:
                if old:
                    moonraker('/server/webcams/item', {k: v for k, v in old.items() if k != 'source'})
                else:
                    current = existing_webcam(moonraker('/server/webcams/list')['webcams'])
                    if current:
                        moonraker('/server/webcams/item?uid='+current['uid'], method='DELETE')
            except (URLError, OSError, ValueError, KeyError) as exc:
                print('Camera files restored; could not restore Fluidd entry: '+str(exc), file=sys.stderr)
        raise
    return dict(status='CAMERA_ENABLED', config=str(config_path), device=value['device'],
                pixel_format=pixel_format, video_verified=True, backup=str(backup),
                stream_url=ROUTE+'stream', snapshot_url=ROUTE+'snapshot',
                fluidd_port=value['fluidd_port'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--enable', action='store_true')
    mode.add_argument('--disable', action='store_true')
    parser.add_argument('--device', help='Stable /dev/v4l/by-id/... path; default autodetects one USB camera')
    parser.add_argument('--data', type=Path, default=Path.home()/'printer_data')
    parser.add_argument('--nginx-site', type=Path, help='Explicit active /etc/nginx site for custom layouts')
    parser.add_argument('--apply', action='store_true', help='Apply config; default only prints a plan')
    args = parser.parse_args(argv)
    config_path = args.data.expanduser().resolve()/'config/m300_camera.conf'
    if config_path.is_symlink():
        raise ValueError('Expected an ordinary camera config file')
    text = config_path.read_text() if config_path.exists() else template()
    value = configuration(text)
    if args.enable or args.disable:
        value['enabled'] = args.enable
    if args.device:
        value['device'] = args.device
    value = configuration(updated_config(text, value))
    if not args.apply:
        print(json.dumps(dict(status='CAMERA_PLAN', config=str(config_path), camera=value,
            changes_applied=False, next_command='python3 install-camera.py --apply'), indent=2))
        return
    if os.geteuid() == 0:
        raise ValueError('Run as the Klipper/KIAUH account, not root')
    if not config_path.parent.is_dir():
        raise ValueError('Missing printer_data/config; use --data for your KIAUH installation')
    print(json.dumps(apply(value, config_path, text, args.nginx_site), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, configparser.Error, subprocess.CalledProcessError) as error:
        sys.exit('M300 camera: '+str(error))
