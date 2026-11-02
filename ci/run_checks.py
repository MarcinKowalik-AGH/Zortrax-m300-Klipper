#!/usr/bin/env python3
"""Public source and register-model checks; real Klippy is FILEOUTPUT only."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from project import ROOT, KIT, META, digest, source_digest, upstream_archive, pristine_tree, stage_host_update, stage_host_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--dictionary', type=Path,
                        help='Fresh compiled MCU dictionary; enables real Klippy tests')
    args = parser.parse_args()
    report = ROOT / '.ci/reports'
    report.mkdir(parents=True, exist_ok=True)
    (report / 'VALIDATION.json').unlink(missing_ok=True)
    (ROOT / 'mcu/evidence').mkdir(exist_ok=True)
    rows = []

    def run(name, command, cwd=ROOT, expected_tests=None):
        started = time.monotonic()
        result = subprocess.run([str(item) for item in command], cwd=cwd,
                                capture_output=True, text=True, timeout=180)
        output = result.stdout + result.stderr
        (report / (name + '.log')).write_text(output)
        row = {'name': name, 'returncode': result.returncode,
               'seconds': round(time.monotonic() - started, 3)}
        rows.append(row)
        (report / 'CHECKS.json').write_text(json.dumps(rows, indent=2) + '\n')
        if result.returncode:
            print(output[-12000:], file=sys.stderr)
            raise RuntimeError('Check failed: ' + name)
        if expected_tests is not None:
            count = re.search(r'Ran (\d+) tests?', output)
            if not count or int(count[1]) != expected_tests:
                raise RuntimeError('Unexpected test census: ' + name)
            row['tests'] = expected_tests
        print(json.dumps(row), flush=True)

    for folder in ('host/klippy', 'ci'):
        for path in (ROOT / folder).rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    archive = upstream_archive(args.archive)
    pristine = pristine_tree(archive)
    host = stage_host_update(ROOT / '.ci/host-update')
    run('host_package_integrity', [sys.executable, 'VERIFY.py'], cwd=host)
    run('host_tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        cwd=host, expected_tests=META['self_contained_host_tests'])
    run('repository_contracts', [sys.executable, '-m', 'unittest', 'discover',
                                '-s', 'tests', '-p', 'test_repository.py', '-v'], expected_tests=8)
    run('step_equivalence', [sys.executable, KIT / 'tools/test_stepfast.py',
                            '--upstream', pristine, '--report', report / 'STEP.json'])
    run('autocooling', [sys.executable, KIT / 'tools/test_autocool.py',
                        '--upstream', pristine, '--report', report / 'AUTOCOOL.json'])
    run('guard_snapshot', [sys.executable, ROOT / 'mcu/tests/test_guard_snapshot.py',
                          '--upstream', pristine])
    run('native_heater_checks', [sys.executable, ROOT / 'mcu/tests/test_verify_gain.py',
                                '--upstream', pristine])
    run('startup_epochs', [sys.executable, KIT / 'tests/test_startup_epoch.py'], expected_tests=5)
    timer = report / 'timer-test'
    run('timer_compile', ['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                          KIT / 'tests/test_m300_timer_deadline.c', '-o', timer])
    run('timer_execute', [timer])
    factory = report / 'factory-test'
    run('factory_decoder_compile', ['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                                    KIT / 'tests/test_m300_factory.c', '-o', factory])
    run('factory_decoder_execute', [factory])
    if args.dictionary:
        host_tree = stage_host_tree(pristine)
        run('real_installer_migration', [sys.executable, ROOT / 'ci/validate_install.py',
            '--root', host_tree, '--output', ROOT / '.ci/installed-config'])
        run('real_installer_r153_migration', [sys.executable, ROOT / 'ci/validate_install.py',
            '--root', host_tree, '--output', ROOT / '.ci/installed-r153', '--baseline', 'r153'])
        run('native_host_reconnect_policy', [sys.executable, ROOT / 'ci/validate_host_reconnect.py',
            '--root', host_tree, '--package', host])
        fixture = ROOT / '.ci/installed-config/printer.cfg'
        run('actual_klippy_fileoutput', [sys.executable, ROOT / 'ci/validate_native_process.py',
            '--root', host_tree, '--config', fixture, '--dictionary', args.dictionary.resolve(),
            '--output', ROOT / '.ci/fileoutput'])
    summary = {'status': 'PASS_M300_PUBLIC_SOFTWARE_CHECKS', 'checks': rows,
               'source_sha256': source_digest(),
               'compiled_dictionary_sha256': digest(args.dictionary) if args.dictionary else None,
               'host_tests': META['self_contained_host_tests'], 'repository_tests': 8,
               'actual_klippy_fileoutput_executed': bool(args.dictionary),
               'physical_uart': False, 'physical_hardware': False, 'flashed': False}
    (report / 'VALIDATION.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'status': summary['status'], 'checks': len(rows)}))


if __name__ == '__main__':
    main()
