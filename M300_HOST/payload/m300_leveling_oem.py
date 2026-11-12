# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 1.3.1 M07 dialogs: one text model for OLED and Fluidd.

Font pixels, line breaks, descriptor associations and layout come from the
supplied application. No hardware access or procedure action lives here.
"""
import base64
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

ASSET_SHA256 = '2a681b7a04acf39b9d4a2cbbec99a781fc22f6f695c9f0ddcc33b923da9f9caf'
LANGUAGES = ('EN', 'PL', 'FR', 'DE', 'ES')
SCREENS = {'WAIT_PREPARE': '0x8021db0', 'WAIT_WARNING': '0x8021db0',
           'WAIT_TIGHTEN': '0x8021dbc', 'HOMING': '0x8021c60',
           'REVIEW': '0x8021e4c', 'COMPLETE': '0x8021e4c'}
ADJUST = {('rear_left', 'LOOSEN'): '0x8021dec',
          ('rear_right', 'LOOSEN'): '0x8021df8',
          ('front', 'LOOSEN'): '0x8021e04',
          ('rear_left', 'TIGHTEN'): '0x8021e10',
          ('rear_right', 'TIGHTEN'): '0x8021e1c',
          ('front', 'TIGHTEN'): '0x8021e28'}


@lru_cache(maxsize=1)
def assets():
    raw = Path(__file__).with_name('m300_leveling_oem_131.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != ASSET_SHA256:
        raise ValueError('M300 OEM leveling text/font integrity mismatch')
    return json.loads(raw)


def text(text_id, language):
    return assets()['texts'][str(text_id)]['languages'][language]


def turn_unit(instruction, language):
    turns = float(instruction['turns'])
    # The wizard's front branch uses singular below 2, including fractions.
    # Preserve that OEM wording; rear branches call 0x080159e8 instead.
    if instruction['screw'] == 'front':
        index = 139 if turns < 2. else 140
    elif turns != int(turns):
        index = 141
    elif turns == 1.:
        index = 139
    else:
        index = 140 if 2. <= turns <= 4. else 142
    return text(index, language)


def describe(status, language='EN'):
    language = language if language in LANGUAGES else 'EN'
    state = status.get('state', 'IDLE')
    descriptor = SCREENS.get(state)
    instruction = status.get('instruction') or {}
    if state == 'PROBING':
        stage = status.get('measurement_stage')
        descriptor = ('0x8021c60' if stage in ('initial', None) else
                      '0x8021dc8' if stage == 'rear' else
                      '0x8021dd4' if stage == 'front' else '0x8021de0')
    elif state == 'ADJUST':
        descriptor = ADJUST[(instruction['screw'], instruction['action'])]
    elif state == 'FAULT':
        contact = any(part in str(status.get('reason', '')) for part in
                      ('contact', 'PC7', 'trigger', 'NO_RELEASE', 'INITIAL_ACTIVE'))
        descriptor = '0x8021e40' if contact else '0x8021e34'
    record = assets()['descriptors'].get(descriptor)
    if record:
        message = text(record['text_id'], language)
        if state == 'ADJUST':
            # Stock computes millimetres in binary32 before sprintf(double).
            delta = struct.unpack('<f', struct.pack('<f', instruction['delta_mm']))[0]
            message %= (delta, instruction['turns'], turn_unit(instruction, language))
        sprite = '0x%08x' % int(record['sprite'], 16)
    elif state == 'HEATING':
        message, sprite = text(123, language), '0x0801c2b8'
    else:
        # Port-only states remain identified as such in the audit. They never
        # masquerade as a recovered OEM message or successful measurement.
        messages = {
            'WAIT_RETRY': ('Próbki są rozbieżne. Sprawdź dyszę i pole\nkontaktowe. Naciśnij przycisk, aby powtórzyć.',
                           'Samples disagree. Check the nozzle and\ncontact pad. Press the button to retry.'),
            'CANCELLED': ('Poziomowanie anulowane.\nNowy wynik nie został zapisany.',
                          'Calibration cancelled.\nNo new observation saved.'),
            'IDLE': ('Poziomowanie platformy', 'Platform leveling')}
        message = messages.get(state, (str(state), str(state)))[language != 'PL']
        sprite = '0x0801fe34' if state == 'CANCELLED' else '0x0801ca28'
    review = status.get('review')
    diagram = tuple(review) if isinstance(review, list) and len(review) == 5 and state in ('REVIEW', 'COMPLETE') else None
    support = text(105, language) if record and record['flags'] & 0x100 else None
    return dict(text=message+('\n'+support if support else ''), body=message,
                support=support, language=language, descriptor=descriptor,
                text_id=record['text_id'] if record else 123 if state == 'HEATING' else None,
                sprite=None if diagram else sprite, diagram=diagram,
                can_confirm=status.get('can_confirm') is True,
                can_cancel=status.get('can_cancel') is True,
                state=state, reason=str(status.get('reason') or ''))


@lru_cache(maxsize=1)
def font():
    return tuple((g['width'], base64.b64decode(g['bitmap_b64'])) for g in assets()['glyphs'])


@lru_cache(maxsize=512)
def glyph_index(character):
    code = ord(character)
    if code < 384:
        return code
    # The stock UTF-8 mapper scans encoded headers for extended characters.
    return next((i for i, g in enumerate(assets()['glyphs']) if g['encoded'] == code), 0)


@lru_cache(maxsize=512)
def width(line):
    return max(0, sum(font()[glyph_index(c)][0]+1 for c in line)-1)


def draw_text(frame, x, y, line):
    for char in line:
        advance, bitmap = font()[glyph_index(char)]
        for band in range(max(1, (advance+7)//8)):
            for row in range(13):
                bits = bitmap[band*13+row]
                for col in range(8):
                    if bits & (128 >> col):
                        frame.pixel(x+band*8+col, y+row)
        x += advance+1


def draw_sprite(frame, sprite):
    """Right-align a packed sprite at the OEM icon edge."""
    width, height, pixels = sprite
    stride = width // 2
    for column in range(stride):
        offset = (125 - stride + column) * 64 + 7
        frame.raw[offset:offset + height] = pixels[column::stride]


def format_deviation(value):
    return '%.1f' % (0. if -.005 < value < 0. else value)


def render(screen, sprites, frame_type, now=0.):
    sprite = (sprites.get(screen['sprite'], now)
              if screen.get('sprite') and sprites is not None else None)
    return _compose(screen['body'], screen.get('support'), screen.get('diagram'), sprite, frame_type)


@lru_cache(maxsize=64)
def _compose(message, support, diagram, sprite, frame_type):
    frame = frame_type()
    lines = message.split('\n')
    y = int(((48 if support else 60)-len(lines)*12)/2)
    for line in lines:
        draw_text(frame, int((192-width(line))/2), y, line)
        y += 12
    if support:
        draw_text(frame, int((192-width(support))/2), 48, support)
    # ui_animation_service_tick clears the entire right-hand 64-pixel area
    # before drawing, including text ink that overflows its 192-pixel box.
    if diagram is not None or sprite is not None:
        frame.raw[96*64:] = bytes(32*64)
    if diagram is not None:
        # Stock draws a 64x64 diagram into OLED columns offset by 48*4 pixels.
        # Use the selected 400/800 scale upstream, not its hard-coded 1/800.
        for p in range(7, 58):
            for x, y in ((192+p, 7), (192+p, 57), (199, p), (249, p)):
                frame.pixel(x, y)
        values = [format_deviation(value) for value in diagram]
        for point, y, align in ((4, 7, 'left'), (3, 7, 'right'),
                                (2, 26, 'center'), (1, 44, 'left'), (0, 44, 'right')):
            line = values[point]
            x = 10 if align == 'left' else 55-width(line) if align == 'right' else int((64-width(line))/2)+2
            draw_text(frame, 192+x, y, line)
    elif sprite:
        draw_sprite(frame, sprite)
    return frame.wire_bytes()
