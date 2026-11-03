"""Check OEM 1.3.1 Settings callbacks and OLED menu pixels from the private model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from reproduce_procedure_contract import STOCK_SHA, load_model

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host/klippy'))
from extras.m300_oem_graphics import OEMGraphics
from extras.m300_oled_render import Frame
from extras.m300_settings_ui import menu_frame

NODES = dict(settings=0x20000828, setting_light_mode=0x2000085c,
             setting_sound=0x20000924, setting_sleep_mode=0x2000098c,
             setting_sort_mode=0x20000ad0, information=0x20000be4)
# Page, label, callback, settings RAM byte, expected stored value, record ID.
CHOICES = (
    ('light_mode', 'Dynamic', 0x08014e70, 0x20000f80, 0, 1),
    ('light_mode', 'White', 0x08014eb0, 0x20000f80, 1, 1),
    ('light_mode', 'Disabled', 0x08014e30, 0x20000f80, 2, 1),
    ('sound', 'Enabled', 0x080148b8, 0x20000f82, 1, 2),
    ('sound', 'Disabled', 0x08014894, 0x20000f82, 0, 2),
    ('sleep_mode', 'Enabled', 0x08015748, 0x20000f86, 1, 4),
    ('sleep_mode', 'Disabled', 0x08015714, 0x20000f86, 0, 4),
    ('sort_mode', 'Date', 0x08015020, 0x20000f82, 0, 2),
    ('sort_mode', 'Name', 0x0801502a, 0x20000f82, 16, 2),
    ('sort_mode', 'Case-sensitive name', 0x08015034, 0x20000f82, 32, 2),
    ('sort_mode', 'File size', 0x0801503e, 0x20000f82, 48, 2),
)


def run_choice(fw, choice):
    key, label, address, mirror, expected, record = choice
    model = fw.Firmware()
    model.w(mirror, 0 if expected else (16 if key == 'sort_mode' else 1), 1)
    node = NODES['setting_' + key]
    model.w(0x200004e0, node)
    model.w(node + 13, 1, 1)
    for boundary in (0x0800a750, 0x0800e37c, 0x080125dc, 0x08018c40):
        model.stub(boundary, label='boundary')
    model.call(address, limit=3_000_000)
    assert model.u(0x200004e0) == node and model.u(node + 13, 1) == 1
    assert model.u(mirror, 1) == expected, (choice, model.u(mirror, 1))
    writes = [e['args'][0] for e in model.events if e['call'] == '0x800a750']
    assert writes == [record], (choice, writes)
    rgb = [e['args'][:3] for e in model.events if e['call'] == '0x800e37c']
    if key == 'light_mode':
        assert rgb == ([[0, 0, 0]] if label == 'Disabled' else [[1, 1, 1]])
    return dict(setting=key, label=label, callback=hex(address), record=record,
                stored_value=expected, rgb=rgb)


def render(fw, page, selected, sprites, setting=None):
    model = fw.Firmware()
    node = NODES[page]
    model.w(0x200004e0, node)
    model.w(node + 13, selected, 1)
    model.w(0x200015b0, 0, 1)
    if setting:
        address, value = setting
        model.w(address, value, 1)
    model.stub(0x0800c290)  # Physical display transfer only.
    draws = []

    def record(cpu):
        text = model.bytes(cpu.r[0], 80).split(b'\0', 1)[0].decode('ascii')
        draws.append((text, int(cpu.r[1]), int(cpu.r[2])))
        return 0

    model.hook(0x0800f586, record)
    model.call(0x08018c40, limit=3_000_000)
    icon = '0x%08x' % model.u(node + 24)
    labels = tuple(label for label, _, _ in draws if label != '<')
    active = tuple(y // 12 for label, _, y in draws if label == '<')
    frame = Frame()
    frame.raw[:] = model.bytes(0x200016c8, 8192)
    wire = frame.wire_bytes()
    expected = menu_frame(labels, active, selected, Frame, sprites.get(icon))
    assert wire == expected, (page, selected, setting, draws)
    return dict(page=page, labels=labels, active=active, selected=selected,
                icon=icon, sha256=hashlib.sha256(wire).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('working', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    fw, _, instructions = load_model(args.source.resolve(), args.working.resolve())
    sprites = OEMGraphics()
    callbacks = [run_choice(fw, choice) for choice in CHOICES]
    frames = [render(fw, page, selected, sprites)
              for page, count in (('settings', 4), ('information', 4))
              for selected in range(count)]
    frames.extend(render(fw, 'setting_' + key, selected, sprites, (mirror, value))
                  for key, _, _, mirror, value, _ in CHOICES
                  for selected in range({'light_mode': 4, 'sound': 3, 'sleep_mode': 3,
                                         'sort_mode': 5}[key]))
    result = dict(source_sha256=STOCK_SHA, verified_instructions=instructions,
                  callbacks=callbacks, frames=frames)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(status='PASS_OEM_SETTINGS', callbacks=len(callbacks), frames=len(frames))))


if __name__ == '__main__':
    main()
