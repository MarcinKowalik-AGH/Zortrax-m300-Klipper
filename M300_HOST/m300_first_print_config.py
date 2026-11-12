"""Opt-in geometry from the user's 2026-11-11 M300 first-print report.

Never lower the global template or mask a bed-mesh error. Called only with an
explicit qualified-first-print-z request. No hardware commands are issued.
"""
import math
import re
import m300_profile as profile

PROFILE = 'M300-FIRST-PRINT-Z-20261111'
SETTINGS = {
    'stepper_z': {'position_min': ('-0.5', (0., -0.5), '0')},
    'm300_motion': {'z_contact_clearance': ('2', (2., 5.), '5')},
    'm300_calibration': {
        'safe_z': ('5', (3., 5.), '5'),
        'approach_distance': ('6.5', (6., 6.5), '6'),
        'probe_search_margin': ('1', (1.,), '1'),
    },
}


def validate_tree(tree):
    counts = dict.fromkeys(SETTINGS, 0)
    for path, text in tree.items():
        _, chunks, saved = profile.blocks(text)
        # Never silently compete with values saved by Klipper's SAVE_CONFIG.
        decoded = re.sub(r'(?m)^#\*# ?', '', saved)
        for section, block in profile.blocks(decoded)[1]:
            if section.lower() in SETTINGS and any(profile.option(block, key) is not None
                    for key in SETTINGS[section.lower()]):
                raise ValueError('Qualified Z settings conflict with SAVE_CONFIG: '+str(path))
        for section, block in chunks:
            section = section.lower()
            if section not in SETTINGS:
                continue
            counts[section] += 1
            if section == 'm300_motion' and profile.option(block, 'mode', 'native') != 'native':
                raise ValueError('Qualified first-print Z requires native M300 motion')
            for key, (_, allowed, default) in SETTINGS[section].items():
                pattern = r'(?mi)^[ \t]*'+re.escape(key)+r'[ \t]*[:=]'
                if len(re.findall(pattern, block)) > 1:
                    raise ValueError('Duplicate qualified Z option: '+section+'.'+key)
                try:
                    value = float(profile.option(block, key, default))
                except (TypeError, ValueError) as exc:
                    raise ValueError('Invalid qualified Z option: '+section+'.'+key) from exc
                if not math.isfinite(value) or value not in allowed:
                    raise ValueError('Unrecognized qualified Z geometry: '+section+'.'+key+
                                     '; retain/review the existing custom configuration')
    if any(count != 1 for count in counts.values()):
        raise ValueError('Qualified Z requires one existing section of each type: '+str(counts))


def apply_to_plan(desired, root_config, original_tree):
    validate_tree(original_tree)
    paths = {p for p in desired if p.suffix == '.cfg' and
             p.resolve().is_relative_to(root_config.parent.resolve())} | set(original_tree)
    planned = {p: desired.get(p, original_tree.get(p, '').encode()).decode() for p in paths}
    validate_tree(planned)
    # Assemble all new contents before publishing them into the atomic plan.
    changes = {}
    for path, text in planned.items():
        prefix, chunks, saved = profile.blocks(text)
        output = [prefix]
        for section, block in chunks:
            for key, (value, _, _) in SETTINGS.get(section.lower(), {}).items():
                block = profile.set_option(block, key, value)
            output.append(block)
        changes[path] = (''.join(output) + saved).encode()
    desired.update(changes)
