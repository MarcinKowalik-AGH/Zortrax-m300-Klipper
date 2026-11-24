#!/usr/bin/env python3
"""Install the complete M300 Classic host after one KIAUH instance.

Works from the source checkout or the CI-published orange-pi branch. The
base Klipper runtime is checksum-pinned; current M300 files, templates and
Fluidd come from the verified deployment, without a previous printer host.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
REPOSITORY = 'https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper'
BASE_NAME = 'Zortrax_M300_Klipper_v1.0.2'
BASE_SHA256 = '837f754daaf311ed47dbada5d31333318191d1ceca7a92970c4cff2896b20870'
BASE_URL = REPOSITORY+'/releases/download/v1.0.2/'+BASE_NAME+'.zip'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def manifest(folder):
    files = {}
    for line in (folder/'SHA256SUMS').read_text().splitlines():
        checksum, name = line.split('  ', 1)
        path = Path(name)
        if (len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum)
                or path.is_absolute() or '..' in path.parts or name in files):
            raise ValueError('Invalid deployment checksum entry')
        target = folder/path
        if (target.is_symlink() or not target.resolve().is_relative_to(folder.resolve())
                or not target.is_file() or digest(target) != checksum):
            raise ValueError('Deployment checksum mismatch: '+name)
        files[name] = checksum
    return files


def download_base(directory):
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory/(BASE_NAME+'.zip')
    if archive.exists():
        if archive.is_symlink() or digest(archive) != BASE_SHA256:
            raise ValueError('Invalid cached release: '+str(archive))
        return archive
    descriptor, name = tempfile.mkstemp(prefix='.m300-download-', dir=directory)
    temporary = Path(name)
    try:
        print('Downloading the complete pinned Klipper runtime...', flush=True)
        with os.fdopen(descriptor, 'wb') as output:
            with urllib.request.urlopen(BASE_URL, timeout=45) as response:
                shutil.copyfileobj(response, output)
        if digest(temporary) != BASE_SHA256:
            raise ValueError('Downloaded release SHA-256 mismatch')
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def safe_path(name):
    path = Path(name)
    return bool(path.parts) and not path.is_absolute() and '..' not in path.parts


def deployment(directory):
    if (HERE/'M300_HOST').is_dir() and (HERE/'SHA256SUMS').is_file():
        return HERE
    # Fetch the successful CI deployment without switching the user's checkout.
    target = directory/'deployment'
    target.mkdir()
    reference = 'refs/m300-bootstrap/'+uuid.uuid4().hex
    try:
        subprocess.run(['git','-C',str(HERE),'fetch','--depth=1','--no-tags',
                        REPOSITORY+'.git','refs/heads/orange-pi:'+reference], check=True)
        archive = directory/'deployment.tar'
        subprocess.run(['git','-C',str(HERE),'archive','--format=tar',
                        '--output='+str(archive),reference], check=True)
        with tarfile.open(archive) as source:
            for entry in source.getmembers():
                if not safe_path(entry.name) or not (entry.isfile() or entry.isdir()):
                    raise ValueError('Unsafe deployment archive member')
            source.extractall(target, **({'filter':'data'} if hasattr(tarfile,'data_filter') else {}))
    finally:
        subprocess.run(['git','-C',str(HERE),'update-ref','-d',reference], check=False)
    return target


def compose_package(base_archive, current, directory):
    """Combine the immutable core with the latest CI-verified M300 payload."""
    files = manifest(current)
    required = ('install-fresh.py','install-new-host.py','install-orange-pi.py','M300_FLUIDD.zip',
                'BUILD_PROVENANCE.json','MCU/klipper.dict',
                'FIRST_INSTALL/m300_classic_base.cfg',
                'FIRST_INSTALL/m300_classic_services.cfg',
                'FIRST_INSTALL/m300_classic_sensors.cfg',
                'FIRST_INSTALL/requirements-m300.txt')
    if any(name not in files for name in required):
        raise ValueError('The orange-pi deployment lacks the new-host installer. '
                         'Wait for the successful build to publish it, then git pull --ff-only.')
    with zipfile.ZipFile(base_archive) as source:
        for entry in source.infolist():
            if (not safe_path(entry.filename) or Path(entry.filename).parts[0] != BASE_NAME
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe base release archive member')
        source.extractall(directory)
    package = directory/BASE_NAME
    manifest(package)
    base = json.loads((package/'BUILD_PROVENANCE.json').read_text())
    latest = json.loads((current/'BUILD_PROVENANCE.json').read_text())
    if (latest.get('model') != 'M300_CLASSIC' or latest.get('release_stage') != 'VERIFIED'
            or latest.get('upstream_commit') != base.get('upstream_commit')):
        raise ValueError('The deployment requires a different verified Klipper core')
    for name in ('M300_HOST','FIRST_INSTALL','MCU'):
        shutil.rmtree(package/name)
    for name in files:
        if (name.startswith(('M300_HOST/','FIRST_INSTALL/','MCU/'))
                or name in ('install-fresh.py','install-new-host.py','install-orange-pi.py',
                            'M300_FLUIDD.zip','BUILD_PROVENANCE.json')):
            target = package/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current/name, target)
    # Core adaptations beyond upstream and all M300 extras are part of the
    # verified deployment. Do not combine its extras with stock upstream.
    for path in (package/'M300_HOST/payload').iterdir():
        if path.suffix in ('.py','.json'):
            shutil.copyfile(path, package/'KLIPPER_HOST/klippy/extras'/path.name)
    shutil.copyfile(package/'M300_HOST/core/gcode.py', package/'KLIPPER_HOST/klippy/gcode.py')
    (package/'BOOTSTRAP_PROVENANCE.json').write_text(json.dumps(dict(
        base_release='v1.0.2', base_sha256=BASE_SHA256,
        deployment_commit=latest['github_commit'], upstream_commit=base['upstream_commit']),indent=2)+'\n')
    members = sorted(p for p in package.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (package/'SHA256SUMS').write_text(''.join(
        digest(p)+'  '+p.relative_to(package).as_posix()+'\n' for p in members))
    return package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', required=True, help='Enabled printer UART, e.g. /dev/ttyS2')
    parser.add_argument('--baud', type=int, default=750000, help='Must match the printer bootloader')
    parser.add_argument('--port', type=int, help='Existing Fluidd port; otherwise prefer 4480')
    parser.add_argument('--fluidd-root')
    parser.add_argument('--python')
    parser.add_argument('--data')
    parser.add_argument('--klipper-root')
    parser.add_argument('--apply', action='store_true', help='Install; default prints the installation plan')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise ValueError('Run as the account used for KIAUH, not root')
    cache = Path.home()/'m300-releases'
    archive = download_base(cache)
    with tempfile.TemporaryDirectory(prefix='m300-bootstrap-',dir=cache) as temporary:
        directory = Path(temporary)
        current = deployment(directory)
        package = compose_package(archive, current, directory)
        spec = importlib.util.spec_from_file_location('m300_first_install', package/'install-fresh.py')
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        forwarded = ['--serial',args.serial,'--baud',str(args.baud)]
        for key in ('port','fluidd_root','python','data','klipper_root'):
            value = getattr(args,key)
            if value is not None:
                forwarded += ['--'+key.replace('_','-'),str(value)]
        if args.apply:
            forwarded.append('--apply')
        fresh.main(forwarded)


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
        sys.exit('M300 new host: '+str(error))
