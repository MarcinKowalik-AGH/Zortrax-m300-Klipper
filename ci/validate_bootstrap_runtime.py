#!/usr/bin/env python3
"""Exercise the public Git installer with real release assets and Klippy.

No system service, UART, MCU, printer motion or heater is used. This job
checks the exact composed payload used by a first-time installer.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

from project import ROOT, digest, stage_host_update
from test_install_orange_pi import OrangePiInstallerTest
from package_git_deploy import package as package_git_deployment

spec=importlib.util.spec_from_file_location('m300_bootstrap',ROOT/'install-new-host.py')
bootstrap=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


def main():
    cache=ROOT/'.ci/bootstrap-cache'
    archive=bootstrap.download_base(cache)
    with tempfile.TemporaryDirectory(prefix='m300-bootstrap-test-',dir=cache) as temporary:
        base=Path(temporary)
        # Use actual release files for MCU and compiled Fluidd; stage current
        # repository sources just as the full build publishes orange-pi.
        import zipfile
        with zipfile.ZipFile(archive) as source:
            source.extractall(base/'original')
        release=base/'original'/bootstrap.BASE_NAME
        current=base/'deployment';current.mkdir()
        stage_host_update(current/'M300_HOST')
        first=current/'FIRST_INSTALL';first.mkdir()
        for name in ('m300_classic_base.cfg','m300_classic_services.cfg','m300_classic_sensors.cfg',
                     'm300_camera.conf'):
            shutil.copy2(ROOT/'host/config'/name,first/name)
        shutil.copy2(ROOT/'host/requirements-m300.txt',first/'requirements-m300.txt')
        shutil.copytree(release/'MCU',current/'MCU')
        shutil.copy2(release/'M300_FLUIDD.zip',current/'M300_FLUIDD.zip')
        shutil.copy2(release/'BUILD_PROVENANCE.json',current/'BUILD_PROVENANCE.json')
        shutil.copy2(ROOT/'ci/install_fresh.py',current/'install-fresh.py')
        shutil.copy2(ROOT/'ci/install_orange_pi.py',current/'install-orange-pi.py')
        shutil.copy2(ROOT/'ci/install_camera.py',current/'install-camera.py')
        for language in ('en', 'pl'):
            shutil.copy2(ROOT/'docs'/language/'CAMERA.md', current/('CAMERA_'+language.upper()+'.md'))
        shutil.copy2(ROOT/'install-new-host.py',current/'install-new-host.py')
        (current/'SHA256SUMS').write_text(''.join(digest(p)+'  '+p.relative_to(current).as_posix()+'\n'
            for p in sorted(current.rglob('*')) if p.is_file()))
        package=bootstrap.compose_package(archive,current,base/'composed')
        git_deployment=base/'published-orange-pi'
        commit=json.loads((package/'BUILD_PROVENANCE.json').read_text())['github_commit']
        package_git_deployment(package,git_deployment,commit)
        # Exercise what git clone --branch orange-pi actually delivers, not
        # just a hand-built staging fixture with additional source files.
        package=bootstrap.compose_package(archive,git_deployment,base/'from-git')
        spec=importlib.util.spec_from_file_location('m300_bootstrap_fresh',package/'install-fresh.py')
        fresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(fresh)
        fresh.verify(package)
        root=base/'klipper';(root/'klippy').mkdir(parents=True)
        (root/'klippy/klippy.py').write_text('# unused stock KIAUH placeholder\n')
        data=base/'data';config=data/'config';config.mkdir(parents=True)
        (config/'printer.cfg').write_text('[mcu]\nserial: /dev/serial/by-id/<your-mcu-id>\n'
            '[printer]\nkinematics: none\nmax_velocity: 1000\nmax_accel: 1000\n')
        (config/'moonraker.conf').write_text('[server]\nhost: 127.0.0.1\n')
        web=base/'fluidd';web.mkdir();(web/'index.html').write_text('<title>fluidd</title>')
        service_commands=[]

        def execute(*command,**kwargs):
            values=tuple(map(str,command))
            if values[:3]==('systemctl','show','klipper.service'):
                return 'active\n'
            if values[:2]==('sudo','systemctl'):
                service_commands.append(values)
                return ''
            if values[:2]==('sudo','chown'):
                return ''
            if values[0]=='sudo':
                command=command[1:]
            return fresh.run(*command,**kwargs)

        with OrangePiInstallerTest.serving(web) as port:
            backup=fresh.install(package,root,data,Path(sys.executable),Path('/dev/ttyS2'),750000,
                                 web,fluidd_port=port,execute=execute)
        assert (backup/'klipper/klippy/klippy.py').read_text()=='# unused stock KIAUH placeholder\n'
        assert (root/'klippy/extras/m300_native_motion.py').is_file()
        assert (web/'index.html').stat().st_size>100
        assert ('sudo','systemctl','start','klipper.service') in service_commands
        text='\n'.join(p.read_text() for p in config.iterdir())
        assert 'kinematics: cartesian' in text
        assert 'serial: /dev/ttyS2' in text
        assert '[gcode_macro M300_HOME_ALL]' in text
        assert '[camera]\nenabled: False' in (config/'m300_camera.conf').read_text()
        assert 'm300-test01' not in text and 'TEST01_UNQUALIFIED' not in text
        report=dict(status='PASS_PUBLIC_GIT_FIRST_INSTALL_FILEOUTPUT',python=sys.version.split()[0],
                    config_source='PUBLIC_FIRST_INSTALL_TEMPLATES',previous_printer_required=False,
                    serial='/dev/ttyS2',baud=750000,complete_install_transaction=True,
                    system_services_simulated=True,physical_hardware=False)
        output=ROOT/'.ci/reports'/('BOOTSTRAP_PYTHON_'+sys.version.split()[0]+'.json')
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))


if __name__=='__main__':
    main()
