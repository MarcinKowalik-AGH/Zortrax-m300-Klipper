#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# check_fluidd_recovery.py - Odtwarza awarię pustych plików HTML i JavaScript, a następnie sprawdza naprawiony Fluidd w przeglądarkach.
"""Serve the actual release UI and verify recovery from two empty files."""
import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

from install_orange_pi import deploy_web, extract_web, select_fluidd


class StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def fixture_command(*args, capture=False):
    # Use the real filesystem commands on the temporary tree under this test.
    # The HTTP server sees the replacement immediately without an nginx reload.
    assert args[0] == 'sudo', args
    if args[1:] == ('systemctl', 'reload', 'nginx'):
        return
    return subprocess.run(args[1:], check=True, text=True,
                          capture_output=capture).stdout


def read_http(url):
    with urlopen(url, timeout=5) as response:
        assert response.status == 200, url
        return response.read()


def check_browser(browser, url, javascript):
    context = browser.new_context(service_workers='block')
    try:
        page = context.new_page()
        responses = {}
        page.on('response', lambda response: responses.update({response.url: response.status}))
        page.goto(url, wait_until='load')
        page.locator('.v-application.fluidd').first.wait_for(state='visible')
        page.locator('.v-navigation-drawer').first.wait_for(state='attached')
        assert responses.get(url + javascript) == 200, responses
        assert 'fluidd' in page.title().casefold(), page.title()
    finally:
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--chromium-executable')
    parser.add_argument('--browsers', default='chromium,firefox')
    args = parser.parse_args()
    versions = {}
    with TemporaryDirectory(prefix='m300-fluidd-recovery-') as folder:
        fixture = Path(folder)
        source = extract_web(args.archive, fixture / 'package')
        root = fixture / 'existing'
        shutil.copytree(source, root)
        index = source / 'index.html'
        html = index.read_bytes()
        main_script = re.search(rb'<script\b[^>]*\bsrc=["\']\./(assets/[^"\']+\.js)["\']', html)
        assert main_script, 'The packaged Fluidd page needs a JavaScript entrypoint'
        javascript = main_script[1].decode('ascii')
        original_javascript = (source / javascript).read_bytes()
        custom_config = (root / 'config.json').read_bytes() + b'\n'
        (root / 'config.json').write_bytes(custom_config)
        (root / 'index.html').write_bytes(b'')
        (root / javascript).write_bytes(b'')

        with ThreadingHTTPServer(('127.0.0.1', 0),
                                 partial(StaticHandler, directory=root)) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                port = server.server_port
                url = f'http://127.0.0.1:{port}/'
                assert read_http(url) == read_http(url + javascript) == b''
                config = f'http {{ server {{ listen {port}; root "{root}"; }} }}'
                selected, actual_port, _ = select_fluidd(config, port, repair_source=source)
                assert selected == root and actual_port == port
                backup = deploy_web(source, selected, port=actual_port, execute=fixture_command)
                assert backup is not None
                assert (backup / 'index.html').stat().st_size == (backup / javascript).stat().st_size == 0
                assert read_http(url) == html
                assert read_http(url + javascript) == original_javascript
                assert (root / 'config.json').read_bytes() == custom_config
                assert deploy_web(source, root, port=port, execute=fixture_command) is None

                with sync_playwright() as driver:
                    for name in args.browsers.split(','):
                        options = {'headless': True}
                        if name == 'chromium' and args.chromium_executable:
                            options['executable_path'] = args.chromium_executable
                        browser = getattr(driver, name).launch(**options)
                        try:
                            check_browser(browser, url, javascript)
                            versions[name] = browser.version
                        finally:
                            browser.close()
            finally:
                server.shutdown()
                worker.join()

    with args.archive.open('rb') as archive:
        checksum = hashlib.file_digest(archive, 'sha256').hexdigest()
    report = dict(status='PASS_FLUIDD_RECOVERY_BROWSER', archive_sha256=checksum,
                  browsers=versions, html_bytes=len(html),
                  main_javascript_bytes=len(original_javascript), custom_config_preserved=True,
                  physical_printer_tested=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
