#!/usr/bin/env python3
"""First M300 Classic install after a single-printer KIAUH system setup.

Default: read-only plan. --apply replaces only an unused stock Klipper setup.
Does not flash firmware, edit UART/boot settings, home, move or heat the printer.
"""
import argparse
import configparser
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

PACKAGE = Path(__file__).resolve().parent
BAUDS = (115200, 250000, 500000, 750000, 1000000, 1500000)


def run(*args, capture=False, cwd=None):
    result = subprocess.run([str(a) for a in args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None, cwd=cwd)
    return result.stdout


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify(package):
    # Reject missing and modified package members before using package code.
    expected = {}
    for line in (package/'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        p = Path(name)
        if not re.fullmatch('[0-9a-f]{64}', digest) or p.is_absolute() or '..' in p.parts:
            raise ValueError('Invalid release checksum entry')
        target = package/p
        if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Release checksum mismatch: '+name)
        expected[name] = digest
    for name in ('BUILD_PROVENANCE.json', 'install-orange-pi.py',
                 'KLIPPER_HOST/klippy/klippy.py', 'M300_HOST/install.py',
                 'M300_FLUIDD.zip', 'FIRST_INSTALL/requirements-m300.txt',
                 'FIRST_INSTALL/m300_classic_base.cfg', 'FIRST_INSTALL/m300_classic_services.cfg',
                 'FIRST_INSTALL/m300_classic_sensors.cfg'):
        if name not in expected:
            raise ValueError('Missing first-install component: '+name)
    provenance = json.loads((package/'BUILD_PROVENANCE.json').read_text())
    if provenance['model'] != 'M300_CLASSIC' or provenance['release_stage'] != 'VERIFIED':
        raise ValueError('A verified M300 Classic release is required')
    return provenance


def refuse_existing(config, root):
    if root.is_symlink() or config.is_symlink():
        raise ValueError('First install requires ordinary Klipper/config paths')
    if (root/'klippy/extras/m300_mcu.py').exists():
        raise ValueError('M300 is already installed; use install-orange-pi.py')
    if not (root/'klippy/klippy.py').is_file():
        raise ValueError('Install one Klipper instance with KIAUH first')
    if config.exists():
        # Only the known empty KIAUH shell may be replaced. Refuse SAVE_CONFIG,
        # heaters/motors and every unrecognized user section or command.
        text = config.read_text()
        allowed = {'mcu','printer','virtual_sdcard', 'display_status', 'pause_resume', 'respond', 'include fluidd.cfg'}
        sections = set(re.findall(r'^\s*\[([^]\n]+)\]', text, re.M))
        if '#*#' in text or not sections <= allowed:
            raise ValueError('Existing printer configuration is not an empty KIAUH setup')
        parser=configparser.ConfigParser(interpolation=None,inline_comment_prefixes=('#',';'))
        try:parser.read_string(text)
        except configparser.Error as exc:raise ValueError('Invalid KIAUH shell configuration') from exc
        for name in parser.sections():
            values=dict(parser[name])
            if name=='mcu':
                valid=values=={'serial':'/dev/serial/by-id/<your-mcu-id>'}
            elif name=='printer':
                valid=values=={'kinematics':'none','max_velocity':'1000','max_accel':'1000'}
            elif name=='virtual_sdcard':
                valid=set(values)<= {'path','on_error_gcode'} and values.get('on_error_gcode','CANCEL_PRINT')=='CANCEL_PRINT'
            else:valid=not values
            if not valid:raise ValueError('Existing printer configuration is not an empty KIAUH setup')
    for name in ('m300_services.cfg', 'm300_temperature_sensors.cfg', 'm300_settings.json',
                 'm300_operations.cfg', 'klipper_calibration.cfg', 'm300_display.cfg'):
        if (config.parent/name).exists():
            raise ValueError('Existing printer data must be migrated, not overwritten: '+name)


def render_config(package, dest, data, serial, baud, machine):
    host = package/'M300_HOST'
    replacements = {'@DATA@':str(data), '@SERIAL@':str(serial), '@BAUD@':str(baud), '@MACHINE@':machine}
    files = {'printer.cfg':'m300_classic_base.cfg',
             'm300_services.cfg':'m300_classic_services.cfg',
             'm300_temperature_sensors.cfg':'m300_classic_sensors.cfg'}
    for output, source in files.items():
        text = (package/'FIRST_INSTALL'/source).read_text()
        for key, value in replacements.items():
            text = text.replace(key, value)
        if re.search(r'@[A-Z_]+@', text):
            raise ValueError('Unresolved first-install configuration token')
        (dest/output).write_text(text)
    for name in ('m300_operations.cfg', 'klipper_calibration.cfg', 'm300_display.cfg'):
        shutil.copy2(host/'payload'/name, dest/name)


def moonraker_config(text):
    # Our host is an immutable source snapshot and Fluidd is a prebuilt extension.
    # Remove only exact stock updater sections; preserve custom sources and auth.
    blocks = re.split(r'(?=^\[)', text, flags=re.M)
    out = []
    for block in blocks:
        if re.match(r'\[update_manager (?:klipper|fluidd|fluidd-config)\]\s*\n', block):
            if re.search(r'(?m)^\s*(?:origin|repo)\s*[:=]\s*(?:https://github.com/)?(?:Klipper3d/klipper|fluidd-core/(?:fluidd|fluidd-config))(?:\.git)?\s*$', block):
                continue
            raise ValueError('Custom updater needs manual review before first install')
        out.append(block)
    return ''.join(out)


def check_service(data, root, python):
    info = dict(line.split('=',1) for line in run('systemctl','show','klipper.service',
        '--property=User,ExecStart,EnvironmentFiles',capture=True).splitlines() if '=' in line)
    if info.get('User') != run('id','-un',capture=True).strip():
        raise ValueError('Klipper service must run as the current KIAUH account')
    command = info.get('ExecStart','')
    envs = info.get('EnvironmentFiles','')
    env_path = data/'systemd/klipper.env'
    environment = env_path.read_text() if env_path.is_file() else ''
    settings = command+'\n'+environment
    if str(python) not in command or str(root/'klippy/klippy.py') not in settings:
        raise ValueError('Expected the standard single-printer KIAUH Klipper service paths')
    if str(data/'config/printer.cfg') not in settings or str(data/'comms/klippy.sock') not in settings:
        raise ValueError('Klipper service config/socket must point to the selected printer_data')
    if environment and str(env_path) not in envs:
        raise ValueError('Klipper service does not load the expected environment file')


def require_unused_klipper(printer):
    info = printer('/server/info')
    if info.get('klippy_state') not in ('disconnected', 'startup', 'error'):
        raise ValueError('First install expects an unused, unconfigured KIAUH instance')


def install(package, root, data, python, serial, baud, web_root, *, fluidd_port=None, execute=run):
    config = data/'config/printer.cfg'
    refuse_existing(config, root)
    data.mkdir(parents=True,exist_ok=True)
    (data/'gcodes').mkdir(exist_ok=True)
    (data/'config').mkdir(exist_ok=True)
    moon = data/'config/moonraker.conf'
    moonraker_config(moon.read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = root.parent/('m300-first-install-backup-'+stamp)
    backup.mkdir(mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix='m300-first-stage-',dir=root.parent))
    moved = False
    installed = []
    web_backup = None
    try:
        source = stage/'klipper'
        shutil.copytree(package/'KLIPPER_HOST', source)
        dest = stage/'config';dest.mkdir()
        render_config(package,dest,data,serial,baud,'M300_CLASSIC_'+stamp)
        # Refuse incomplete/foreign host payloads before touching the active tree.
        updater = module('m300_first_update',package/'M300_HOST/install.py')
        updater.verify();updater.check_api(source)
        dependencies = stage/'dependencies'
        dependencies.mkdir()
        execute(python, '-m', 'pip', 'install', '--target', dependencies, '-r',
                package/'FIRST_INSTALL/requirements-m300.txt')
        # Python loads Klippy from this directory with the service's existing
        # interpreter. Stage the pinned dependencies beside the script so they
        # move and roll back with Klipper, leaving the KIAUH venv intact.
        for dependency in dependencies.iterdir():
            target = source/'klippy'/dependency.name
            if target.exists() or target.with_suffix('.py').exists():
                raise ValueError('Python dependency conflicts with Klipper: '+dependency.name)
            dependency.rename(target)
        execute(python,'-c','import chelper; chelper.get_ffi()',cwd=source/'klippy')
        deploy = module('m300_first_deploy',package/'install-orange-pi.py')
        archive = package/'M300_FLUIDD.zip'
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Unsafe Fluidd archive member')
            bundle.extractall(stage/'web')
        build_id = hashlib.sha256(archive.read_bytes()).hexdigest()
        web = deploy.verified_web_root(stage/'web/fluidd-m300')
        (web/'.m300-fluidd-build').write_text(build_id+'\n')
        refuse_existing(config, root)
        updated_moon = moonraker_config(moon.read_text())
        shutil.copy2(moon,backup/'moonraker.conf')
        if config.exists():shutil.copy2(config,backup/'printer.cfg')
        (backup/'RECEIPT.json').write_text(json.dumps(dict(source_commit=json.loads(
            (package/'BUILD_PROVENANCE.json').read_text())['github_commit'],root=str(root),data=str(data)),indent=2)+'\n')
        active_state = execute('systemctl', 'show', 'klipper.service',
                               '--property=ActiveState', '--value', capture=True).strip()
        if active_state not in ('active', 'inactive', 'failed'):
            raise ValueError('Wait until the stock Klipper service is fully started or stopped')
        execute('sudo','systemctl','stop','klipper.service')
        try:
            root.rename(backup/'klipper');moved=True
            source.rename(root)
            for path in dest.iterdir():
                target=config.parent/path.name
                updater.atomic_write(target,path.read_bytes());installed.append(target)
            updater.atomic_write(moon,updated_moon.encode())
            execute('sudo','systemctl','start','klipper.service')
            execute('sudo','systemctl','restart','moonraker.service')
            web_backup = deploy.deploy_web(web,web_root,build_id,execute=execute)
            if fluidd_port is not None:
                deploy.save_install_state(config.parent,web_root,fluidd_port)
        except BaseException:
            execute('sudo','systemctl','stop','klipper.service')
            try:
                if moved:
                    if root.exists():root.rename(stage/'failed-klipper')
                    (backup/'klipper').rename(root)
                for target in installed:target.unlink(missing_ok=True)
                if (backup/'printer.cfg').exists():shutil.copy2(backup/'printer.cfg',config)
                shutil.copy2(backup/'moonraker.conf',moon)
                deploy.restore_web(web_root,web_backup,execute=execute)
            finally:
                if active_state == 'active':
                    execute('sudo','systemctl','start','klipper.service')
                execute('sudo','systemctl','restart','moonraker.service')
            raise
        return backup
    finally:
        shutil.rmtree(stage)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial',required=True,type=Path,help='Enabled Linux UART, e.g. /dev/ttyS1 or /dev/serial0')
    parser.add_argument('--baud',type=int,choices=BAUDS,default=750000,help='Must match the printer bootloader setting')
    parser.add_argument('--data',type=Path,default=Path.home()/'printer_data')
    parser.add_argument('--klipper-root',type=Path,default=Path.home()/'klipper')
    parser.add_argument('--python',type=Path,default=Path.home()/'klippy-env/bin/python')
    parser.add_argument('--port',type=int,default=None,help='Existing Fluidd port; prefer 4480, else unambiguous nginx detection')
    parser.add_argument('--fluidd-root',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        if os.geteuid()==0:raise ValueError('Run as the KIAUH account, not root')
        if not (3,10)<=sys.version_info[:2]<=(3,12):raise ValueError('First install supports Python 3.10-3.12')
        provenance=verify(PACKAGE)
        root,data,python=args.klipper_root.absolute(),args.data.absolute(),args.python.absolute()
        for path in (root,data,python,args.serial):
            if any(c in str(path) for c in ('\n','\r','@','#',';')):raise ValueError('Unsupported path character')
        if not args.serial.is_absolute() or not stat.S_ISCHR(args.serial.stat().st_mode):
            raise ValueError('Select an existing UART character device')
        if not os.access(args.serial,os.R_OK|os.W_OK):raise ValueError('Current account needs read/write access to the UART')
        if not python.is_file():raise ValueError('Install Klipper with KIAUH first')
        refuse_existing(data/'config/printer.cfg',root)
        if not (data/'config/moonraker.conf').is_file():raise ValueError('Install Moonraker with KIAUH first')
        moonraker_config((data/'config/moonraker.conf').read_text())
        check_service(data,root,python)
        deploy=module('m300_first_deploy_plan',PACKAGE/'install-orange-pi.py')
        run('sudo','-v')
        web,fluidd_port,selection=deploy.select_fluidd(
            run('sudo','nginx','-T',capture=True),args.port,args.fluidd_root)
        # Moonraker's server status is available while stock Klipper is stopped.
        require_unused_klipper(deploy.printer)
        plan=dict(status='PLAN_FIRST_M300_INSTALL',source_commit=provenance['github_commit'],
                  serial=str(args.serial),baud=args.baud,klipper=str(root),data=str(data),
                  fluidd_root=str(web),fluidd_port=fluidd_port,selection=selection,
                  mcu_flashed=False,motion_or_heating_sent=False)
        if args.apply:
            plan['backup']=str(install(PACKAGE,root,data,python,args.serial,args.baud,web,
                                       fluidd_port=fluidd_port))
            plan['status']='INSTALLED_FIRST_M300_CHECK_READY'
        print(json.dumps(plan,indent=2))
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as exc:
        parser.exit(1,'M300 first install stopped: '+str(exc)+'\n')


if __name__=='__main__':main()
