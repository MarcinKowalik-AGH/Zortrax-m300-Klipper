#!/usr/bin/env python3
"""Install the verified M300 Classic host and Fluidd on an existing Orange Pi."""
import argparse
import hashlib
import json
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


def run(*args, capture=False, cwd=None):
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                            cwd=cwd)
    return result.stdout


def printer(endpoint):
    with urlopen(MOONRAKER + endpoint, timeout=5) as response:
        return json.load(response)['result']


def require_idle():
    info = printer('/printer/info')
    stats = printer('/printer/objects/query?print_stats')['status']['print_stats']
    if info['state'] != 'ready' or stats['state'] not in ('standby', 'complete', 'cancelled', 'error'):
        raise ValueError('Wait until Klipper is Ready and the printer is idle')
    return info


def nginx_root(config, port):
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


def apply_host(host, args, plan):
    if plan['status'] == 'ALREADY_M300_R16_12':
        return
    if plan['status'] != 'PLAN_M300_R16_12':
        raise ValueError('Unexpected host install plan')
    require_idle()
    run('sudo', 'systemctl', 'stop', 'klipper.service')
    try:
        run(sys.executable, 'install.py', *args, '--apply', cwd=host)
    finally:
        run('sudo', 'systemctl', 'start', 'klipper.service')


def wait_ready():
    for _ in range(45):
        try:
            if printer('/printer/info')['state'] == 'ready':
                return
        except URLError:
            pass
        time.sleep(1)
    raise ValueError('Klipper did not reach Ready after the host update')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4080, help='Existing Fluidd nginx port')
    parser.add_argument('--fluidd-root', type=Path, help='Override nginx web root detection')
    args = parser.parse_args()
    if not (PACKAGE / 'SHA256SUMS').is_file():
        parser.exit(1, 'Run this installer from the extracted GitHub Actions artifact.\n')
    if os.geteuid() == 0:
        parser.exit(1, 'Run as the Klipper account on the Orange Pi.\n')
    try:
        run('sha256sum', '-c', '--quiet', 'SHA256SUMS', cwd=PACKAGE)
        info = require_idle()
        host = PACKAGE / 'M300_HOST_R16_12_NORMAL_UI'
        host_args = ('--root', info['klipper_path'], '--config', info['config_file'])
        plan = json.loads(run(sys.executable, 'install.py', *host_args, cwd=host, capture=True))
        run('sudo', '-v')
        config = run('sudo', 'nginx', '-T', capture=True)
        root = verified_web_root(args.fluidd_root or nginx_root(config, args.port))
        archive = PACKAGE / 'M300_FLUIDD_1_37_7_R16_12.zip'
        build_id = hashlib.sha256(archive.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory(prefix='m300-fluidd-') as temp:
            with ZipFile(archive) as bundle:
                bundle.extractall(temp)
            source = verified_web_root(Path(temp) / 'fluidd-m300')
            (source / '.m300-fluidd-build').write_text(build_id + '\n')
            apply_host(host, host_args, plan)
            wait_ready()
            run(sys.executable, 'setup_fluidd.py', '--apply', '--config-directory',
                Path(info['config_file']).parent, cwd=host)
            backup = deploy_web(source, root, build_id)
        print(json.dumps({'status': 'INSTALLED_M300_R16_12_FULL', 'fluidd_root': str(root),
                          'fluidd_backup': str(backup) if backup else None, 'mcu_flashed': False}))
    except (ValueError, OSError, KeyError, IndexError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'M300 installation stopped: {exc}\n')


if __name__ == '__main__':
    main()
