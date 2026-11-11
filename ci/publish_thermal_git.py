#!/usr/bin/env python3
"""Publish an already-tested host package to the existing Git deployment tree.
No printer, SSH, service or heating access. All install tests use a temporary
filesystem and mock only the API-presence check of that dummy Klipper tree.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

HOST_DIR = 'M300_HOST_R16_12_NORMAL_UI'
PACKAGE_SHA = '22b34f3d41e4c9213dc5d841d12882bf40759dea1faa33c4ccca5010c910713c'
SOURCE_SHA = 'b8f76f0839508858462af234007e76b78d7e6293'
SOURCE_RUN = '43072164421'
EXPECTED_PARENT = '7c59b7763b690c14cc4f77a838cf82066f842bb7'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '.git' not in p.relative_to(root).parts
            and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def old_deployment_upgrade(old_host, candidate):
    """Exercise actual file acceptance, included cfg migration and rollback."""
    sys.path.insert(0, str(candidate))
    spec = importlib.util.spec_from_file_location('install_thermal_deploy', candidate/'install.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with tempfile.TemporaryDirectory(prefix='m300-upgrade-test-') as tmp:
        root = Path(tmp)/'klipper'
        extras = root/'klippy/extras'
        extras.mkdir(parents=True)
        for name in installer.NAMES:
            old = old_host/'payload'/name
            if old.is_file():
                shutil.copy2(old, extras/name)
        cfgdir = Path(tmp)/'printer_data/config'
        cfgdir.mkdir(parents=True)
        config = cfgdir/'printer.cfg'
        saved = '#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [extruder]\n#*# pid_kp = 15.123\n'
        config.write_text('[mcu]\nserial: /dev/ttyS1\nbaud: 1500000\n[include heaters.cfg]\n'+saved)
        heaters = cfgdir/'heaters.cfg'
        heaters.write_text(
            '[extruder]\nsensor_type: M300_HOTEND_STOCK_LINEAR_LAB\nmax_temp: 270\n'
            'rotation_distance: 26.133\npid_kp: 15.123\n'
            '[heater_bed]\nsensor_type: M300_BED_STOCK_TABLE_LAB\nmax_temp: 120\npid_kp: 60.123\n')
        original = {p: p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
        with patch.object(installer, 'check_api', return_value=None):
            changes = installer.plan(root, config, thermal_305105=True)
            assert changes, 'Previous deployment should have a thermal upgrade plan'
            assert all(p.read_bytes() == b for p,b in original.items()), 'Plan mutated a file'
            receipt = installer.apply(root, config, changes)
            assert 'max_temp: 310' in heaters.read_text()
            assert 'max_temp: 120' in heaters.read_text()
            assert 'rotation_distance: 26.133' in heaters.read_text()
            assert 'pid_kp: 15.123' in heaters.read_text()
            assert 'pid_kp: 60.123' in heaters.read_text()
            assert config.read_text().endswith(saved)
            assert 'baud: 1500000' in config.read_text()
            assert config.read_text().count('[m300_temperature_policy]') == 1
            assert 'hotend_target_max: 305' in config.read_text()
            assert 'bed_target_max: 105' in config.read_text()
            assert installer.plan(root, config, thermal_305105=True) == [], 'Upgrade not idempotent'
            installer.rollback(receipt, root, config)
            assert all(p.read_bytes() == b for p,b in original.items()), 'Rollback changed prior bytes'
        result = {'previous_payload_upgrade': 'PASS', 'read_only_plan': 'PASS',
                  'included_heater_config': 'PASS', 'pid_rotation_distance_uart_preserved': 'PASS',
                  'save_config_preserved': 'PASS', 'idempotent_apply': 'PASS', 'exact_rollback': 'PASS',
                  'hardware_access': False}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--deployment', type=Path, required=True)
    ap.add_argument('--artifact', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    a = ap.parse_args()
    target, artifact, source = a.deployment.resolve(), a.artifact.resolve(), a.source.resolve()
    parent = subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD'],text=True).strip()
    assert parent == EXPECTED_PARENT, 'Deployment advanced; do not overwrite another publication'
    assert not subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True).strip()
    pkg = artifact/'M300_HOST_305_105_R1.zip'
    assert sha(pkg) == PACKAGE_SHA
    validation = json.loads((artifact/'VALIDATION.json').read_text())
    assert validation['software_tests'] == 768 and validation['software_result'] == 'PASS'
    assert validation['operating_target_max'] == {'extruder':305,'heater_bed':105}
    assert validation['sensor_shutdown_limits'] == {'extruder':310,'heater_bed':120}
    assert str(validation['workflow_run_id']) == SOURCE_RUN
    previous = files(target)
    protected = {n:d for n,d in previous.items() if n.startswith('MCU/')
                 or n in ('install-orange-pi.py','M300_FLUIDD_1_37_7_R16_12.zip')}
    assert len(protected) >= 3
    with tempfile.TemporaryDirectory(prefix='m300-publish-') as tmp:
        stage = Path(tmp)/HOST_DIR
        stage.mkdir()
        with zipfile.ZipFile(pkg) as z:
            assert z.testzip() is None
            for entry in z.infolist():
                assert (stage/entry.filename).resolve().is_relative_to(stage)
                assert Path(entry.filename).suffix.lower() not in ('.ttf','.otf','.woff','.woff2')
            z.extractall(stage)
        # Confirm payload is the source change already accepted on main.
        meta = json.loads((source/'PORT.json').read_text())
        for name in meta['host_update_files']:
            assert (source/'host/klippy/extras'/name).read_bytes() == (stage/'payload'/name).read_bytes()
        for cfg in (source/'host/config').glob('*.cfg'):
            assert cfg.read_bytes() == (stage/'payload'/cfg.name).read_bytes()
        subprocess.run([sys.executable,'VERIFY.py'],cwd=stage,check=True)
        proc = subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                              cwd=stage,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (artifact/'RETEST_HOST.log').write_text(proc.stdout)
        print(proc.stdout[-1500:])
        assert proc.returncode == 0 and re.search(r'Ran 768 tests\b',proc.stdout)
        checks = old_deployment_upgrade(target/HOST_DIR,stage)
        for folder in list(stage.rglob('__pycache__')):
            shutil.rmtree(folder)
        for p in stage.rglob('*.pyc'):
            p.unlink()
        # The unpacked package itself remains byte-for-byte identical to the
        # verified archive; only the distribution provenance is new.
        with zipfile.ZipFile(pkg) as z:
            assert all((stage/n).read_bytes()==z.read(n) for n in z.namelist())
        shutil.rmtree(target/HOST_DIR)
        shutil.copytree(stage,target/HOST_DIR)
    provenance_path = target/'BUILD_PROVENANCE.json'
    provenance = json.loads(provenance_path.read_text())
    provenance['prior_distribution_provenance'] = {
        k: provenance.get(k) for k in ('github_commit','github_run_id','distribution_version','mcu_release','host_update')}
    provenance.update(
        distribution_version='v1.0.0-beta.23+thermal305.1',
        host_update='R16.12 + M300-305-105-R1',
        github_commit=SOURCE_SHA,
        github_run_id=os.environ['GITHUB_RUN_ID'],
        host_source_run_id=SOURCE_RUN,
        host_package_sha256=PACKAGE_SHA,
        operating_target_max={'extruder':305,'heater_bed':105},
        sensor_shutdown_limits={'extruder':310,'heater_bed':120},
        hardware_acceptance=validation['hardware_acceptance'],
        mcu_changed=False, fluidd_changed=False, installer_changed=False,
        installed_on_printer=False)
    provenance_path.write_text(json.dumps(provenance,indent=2)+'\n')
    validation.update(git_deployment_parent=parent,git_publication_run_id=os.environ['GITHUB_RUN_ID'],
                      deployment_tests=checks,retained_files_sha256=protected,
                      host_package_sha256=PACKAGE_SHA,software_regression_repeated=768)
    (target/'THERMAL305_VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
    (target/'README.md').write_text(
        '# M300 Classic — instalacja Git na Orange Pi\n\n'
        '**Aktualny host: R16.12 + M300-305-105-R1. Maksymalne nastawy: ekstruder305°C, stół105°C.** '
        'Odcięcia czujników:310/120°C. MCU, Fluidd i dotychczasowy instalator bez zmian.\n\n'
        '## Aktualizacja istniejącej instalacji\n\n'
        'Drukarka musi być bezczynna, Klipper Ready. Uruchom jako użytkownik Klippera, nie root:\n\n'
        '```bash\n'
        'git -C "$HOME/m300-orange-pi" pull --ff-only &&\n'
        'python3 "$HOME/m300-orange-pi/install-orange-pi.py"\n'
        '```\n\n'
        'Instalator odczytuje aktywne ścieżki Klippera i printer.cfg z lokalnego Moonrakera; '
        'nie zakłada katalogu ~/klipper. Weryfikuje pliki, przygotowuje kopię/receipt, '
        'zatrzymuje Klippera na czas aktualizacji i uruchamia go ponownie. '
        'Nie zmienia portu Fluidd, nie flashuje MCU i nie uruchamia grzania.\n\n'
        '## Pierwsze pobranie tej gałęzi\n\n'
        '```bash\n'
        'git clone --branch orange-pi --single-branch https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$HOME/m300-orange-pi" &&\n'
        'python3 "$HOME/m300-orange-pi/install-orange-pi.py"\n'
        '```\n\n'
        'Nie używaj clone, jeżeli katalog już istnieje. Gdy Git zgłosi lokalne zmiany, '
        'nie wykonuj reset --hard ani kasowania katalogu w ciemno.\n\n'
        '## Sprawdzenie w konsoli Fluidd\n\n'
        '```gcode\nZORTRAX_TEMPERATURE_LIMITS\nSTATUS\n```\n\n'
        'Oczekiwane revision=M300-305-105-R1, bound=true, target_limits305/105 '
        'i sensor_shutdown_limits310/120. To polecenia informacyjne.\n\n'
        '## Walidacja\n\n'
        '768 testów hosta ponownie PASS; przejście z poprzedniej gałęzi orange-pi, '
        'dołączone pliki konfiguracyjne, zachowanie PID/UART/rotation_distance, '
        'idempotencja i rollback sprawdzone na tymczasowym systemie plików. '
        'Test305/105 na sprzęcie został zgłoszony przez użytkownika11.11.2026; '
        'nie jest to deklaracja testów wszystkich materiałów. '
        'Raport: THERMAL305_VALIDATION.json.\n\n'
        'Profile Orca są w oddzielnym repozytorium Zortrax-m300-Orca-Slicer. '
        'Ta aktualizacja nie instaluje Orca na Orange Pi ani na komputerze.\n')
    after = files(target)
    assert all(after.get(n)==digest for n,digest in protected.items()), 'MCU/UI/installer changed'
    (target/'SHA256SUMS').write_text(''.join(after[n]+'  '+n+'\n' for n in sorted(after) if n!='SHA256SUMS'))
    subprocess.run(['sha256sum','-c','--quiet','SHA256SUMS'],cwd=target,check=True)
    subprocess.run([sys.executable,'VERIFY.py'],cwd=target/HOST_DIR,check=True)
    print(json.dumps({'status':'READY_TO_PUBLISH','deployment_checks':checks,'host_tests':768,
                      'mcu_changed':False,'fluidd_changed':False,'installer_changed':False}))


if __name__=='__main__':
    main()
