"""Shared staging for CI. Never contacts a printer or changes its config."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
META = json.loads((ROOT / 'PORT.json').read_text())
KIT = ROOT / 'mcu/SOURCE_MCU'
OWNER = '.m300-ci-generated.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_digest():
    inputs = [ROOT / 'PORT.json']
    for directory in ('ci', 'host', 'mcu/SOURCE_MCU', 'mcu/tests', 'tests'):
        inputs.extend(path for path in (ROOT / directory).rglob('*')
                      if path.is_file() and '__pycache__' not in path.parts
                      and path.suffix not in ('.pyc', '.zip', '.log'))
    hasher = hashlib.sha256()
    for path in sorted(set(inputs)):
        hasher.update(str(path.relative_to(ROOT)).encode() + b'\0')
        hasher.update(bytes.fromhex(digest(path)))
    return hasher.hexdigest()


def fresh_directory(path):
    path = Path(path).resolve()
    if path.exists():
        marker = path / OWNER
        if not marker.is_file() or json.loads(marker.read_text()).get('owner') != 'm300-ci':
            raise ValueError('Refusing to replace an unowned directory: ' + str(path))
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / OWNER).write_text(json.dumps({'owner': 'm300-ci'}) + '\n')
    return path


def upstream_archive(path=None):
    path = Path(path).resolve() if path else KIT / 'UPSTREAM_KLIPPER_PINNED.zip'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix('.download')
        try:
            with urllib.request.urlopen(META['upstream_archive_url'], timeout=90) as response:
                with partial.open('wb') as output:
                    shutil.copyfileobj(response, output)
            if digest(partial) != META['upstream_archive_sha256']:
                raise ValueError('Downloaded upstream SHA-256 mismatch')
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
    if digest(path) != META['upstream_archive_sha256']:
        raise ValueError('Pinned upstream SHA-256 mismatch')
    # Historical source tests intentionally use this canonical local path.
    target = KIT / 'UPSTREAM_KLIPPER_PINNED.zip'
    if target.resolve() != path.resolve():
        if not target.exists() or digest(target) != META['upstream_archive_sha256']:
            shutil.copyfile(path, target)
    return target


def pristine_tree(archive):
    spec = importlib.util.spec_from_file_location('m300_build', KIT / 'tools/build.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    target = ROOT / '.ci/pristine'
    builder.stage(archive, target, fresh=target.exists())
    return target


def manifest(folder):
    values = {str(path.relative_to(folder)): digest(path)
              for path in sorted(folder.rglob('*'))
              if path.is_file() and path.name not in ('MANIFEST.json', OWNER)
              and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    (folder / 'MANIFEST.json').write_text(json.dumps(values, indent=2) + '\n')
    return values


def stage_host_update(destination):
    target = fresh_directory(destination)
    shutil.copytree(ROOT / 'host/update_template', target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'docs', target / 'docs', dirs_exist_ok=True)
    payload = target / 'payload'
    payload.mkdir()
    for name in META['host_update_files']:
        shutil.copy2(ROOT / 'host/klippy/extras' / name, payload / name)
    shutil.copy2(ROOT / 'host/config/m300_display.cfg', payload / 'm300_display.cfg')
    manifest(target)
    return target


def stage_host_tree(pristine):
    target = fresh_directory(ROOT / '.ci/host-klipper')
    shutil.copytree(pristine, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'host/klippy', target / 'klippy', dirs_exist_ok=True)
    return target
