"""Exercise the real installer on an isolated source/config fixture, no services."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

from project import ROOT, fresh_directory, stage_host_update


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', choices=('current', 'r153'), default='current')
    parser.add_argument('--organize-config', action='store_true')
    args = parser.parse_args()
    stage = stage_host_update(ROOT / '.ci/install-package')
    spec = importlib.util.spec_from_file_location('real_m300_installer', stage / 'install.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    if args.baseline == 'r153':
        for source in (stage / 'tests/reference/r153').glob('*.py'):
            (args.root / 'klippy/extras' / source.name).write_bytes(source.read_bytes())
    target = fresh_directory(args.output)
    cfg = target / 'printer.cfg'
    original = (ROOT / 'tests/fixtures/printer_r15_5_test.cfg').read_bytes()
    cfg.write_bytes(original)
    installer.verify()
    changes = installer.plan(args.root, cfg, organize_config=args.organize_config)
    assert cfg.read_bytes() == original
    receipt = installer.apply(args.root, cfg, changes)
    assert installer.plan(args.root, cfg, organize_config=args.organize_config) == []
    sections = {name:block for text in installer.profile.read_tree(cfg).values()
                for name,block in installer.profile.blocks(text)[1]}
    assert installer.profile.option(sections['m300_motion'], 'mode') == 'native'
    assert installer.profile.option(sections['m300_motion'], 'z_home_hotend_target') == '180'
    assert installer.profile.option(sections['extruder'], 'rotation_distance') == '26.133'
    assert installer.profile.option(sections['stepper_z'], 'position_max') == '300'
    for name in installer.CONFIG_FILES:
        assert (target / name).is_file()
    installer.rollback(receipt, args.root, cfg)
    assert cfg.read_bytes() == original
    assert not (target / 'm300_tests.cfg').exists()
    installer.apply(args.root, cfg, installer.plan(args.root, cfg, organize_config=args.organize_config))
    assert installer.plan(args.root, cfg, organize_config=args.organize_config) == []
    report = {'status': 'PASS_REAL_INSTALLER', 'config': str(cfg), 'baseline': args.baseline,
              'actual_API_checks': True, 'exact_rollback': True,
              'organized_config': args.organize_config,
              'idempotent': True, 'services_changed': False, 'physical_hardware': False}
    (target / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
