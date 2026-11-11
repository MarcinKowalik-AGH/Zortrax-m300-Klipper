"""Exercise the real installer on an isolated source/config fixture, no services."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from project import ROOT, fresh_directory, stage_host_update


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', choices=('current', 'r153'), default='current')
    parser.add_argument('--organize-config', action='store_true')
    parser.add_argument('--qualified-first-print-z', action='store_true')
    args = parser.parse_args()
    # Each migration scenario owns its package snapshot; never reuse a
    # mutable staging path left by another validator or an interrupted run.
    stage_root = Path(tempfile.mkdtemp(prefix='install-package-', dir=ROOT / '.ci'))
    stage = stage_host_update(stage_root / 'host')
    # Mirror running the packaged installer as a script: its sibling modules
    # belong to this isolated snapshot, not the CI working directory.
    sys.path.insert(0, str(stage))
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
    changes = installer.plan(args.root, cfg, organize_config=args.organize_config,
                             qualified_first_print_z=args.qualified_first_print_z)
    assert cfg.read_bytes() == original
    receipt = installer.apply(args.root, cfg, changes)
    assert installer.plan(args.root, cfg, organize_config=args.organize_config,
                             qualified_first_print_z=args.qualified_first_print_z) == []
    sections = {name:block for text in installer.profile.read_tree(cfg).values()
                for name,block in installer.profile.blocks(text)[1]}
    assert installer.profile.option(sections['m300_motion'], 'mode') == 'native'
    assert installer.profile.option(sections['m300_motion'], 'z_home_hotend_target') == '180'
    assert installer.profile.option(sections['extruder'], 'rotation_distance') == '26.133'
    assert installer.profile.option(sections['stepper_z'], 'position_max') == '300'
    if args.qualified_first_print_z:
        for section, key, value in (('stepper_z', 'position_min', '-0.5'),
                ('m300_motion', 'z_contact_clearance', '2'),
                ('m300_calibration', 'safe_z', '5'),
                ('m300_calibration', 'approach_distance', '6.5'),
                ('m300_calibration', 'probe_search_margin', '1')):
            assert installer.profile.option(sections[section], key) == value
    for name in installer.CONFIG_FILES:
        assert (target / name).is_file()
    installer.rollback(receipt, args.root, cfg)
    assert cfg.read_bytes() == original
    assert not (target / 'm300_tests.cfg').exists()
    installer.apply(args.root, cfg, installer.plan(args.root, cfg, organize_config=args.organize_config,
                             qualified_first_print_z=args.qualified_first_print_z))
    assert installer.plan(args.root, cfg, organize_config=args.organize_config,
                             qualified_first_print_z=args.qualified_first_print_z) == []
    report = {'status': 'PASS_REAL_INSTALLER', 'config': str(cfg), 'baseline': args.baseline,
              'actual_API_checks': True, 'exact_rollback': True,
              'organized_config': args.organize_config,
              'qualified_first_print_z': args.qualified_first_print_z,
              'idempotent': True, 'services_changed': False, 'physical_hardware': False}
    (target / 'REPORT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
