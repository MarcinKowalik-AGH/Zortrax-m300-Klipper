# SPDX-License-Identifier: GPL-3.0-or-later
"""M11 pure five-language menu policy and generation-bound navigation.

This module owns *presentation state only*: it must never execute a move,
heater command, SD read, M03 action, or NVM commit. Actions remain owned by
M02/M03/M06/M07/M08/M09 via the existing M300Menu dispatcher.
"""
import hashlib
import json
import math
import unicodedata

LANGS = ('EN', 'PL', 'FR', 'DE', 'ES')
# All supported actions must be routed by m300_menu.select(), not by this
# presentation-only state layer. Unknown actions fail closed in its audit.
MENU_ACTION_KINDS = frozenset((
    'page', 'oled', 'wake', 'browse', 'directory', 'file', 'confirm_print',
    'confirm_sleep', 'confirmed', 'cycle_clean', 'repeat', 'temperatures',
    'temp', 'material', 'material_action', 'motion_home', 'motion_jog',
    'motion_stop', 'service', 'service_stop', 'cal_start', 'cal_refresh',
    'cal_confirm', 'cal_cancel', 'setting', 'set', 'ui_back',
    'atlas_item', 'atlas_open', 'procedure_action', 'fan_test', 'fan_cancel', 'fan_set', 'native_gcode',
))


def clean_label(text, limit=240):
    if not isinstance(text, str):
        text = str(text)
    if len(text) > 8192:
        text = text[:8192]
    text = ''.join(' ' if ch.isspace() or unicodedata.category(ch) in ('Cc','Cf')
                   else ch for ch in text)
    return ' '.join(text.split())[:limit]


def require_rows(rows):
    if not isinstance(rows, (tuple,list)) or len(rows) > 256:
        raise ValueError('M11 row collection must be bounded to 256')
    for i, row in enumerate(rows):
        if not isinstance(row, (tuple, list)) or len(row) != 2:
            raise ValueError('M11 row shape invalid at %d' % i)
        action = row[1]
        if action is None:
            continue  # explicit informative/unavailable element, never clickable
        if not isinstance(action, tuple) or not action or action[0] not in MENU_ACTION_KINDS:
            raise ValueError('M11 unrecognized action at %d' % i)
    return True


def label_pixel_width(label):
    return sum(8 if ch == '©' else 6 for ch in label)


def fit_label(label, width=216, offset=0):
    """Pixel-budgeted text window, never moves/cancels the selected action.

    Selected long rows rotate through a bounded glyph window. Unselected rows
    show a clipped static prefix, avoiding many rapidly moving rows.
    """
    label = clean_label(label, 240)
    if width < 18 or width > 252:
        raise ValueError('M11 width outside safe OLED region')
    if label_pixel_width(label) <= width:
        return label
    if offset < 0 or not isinstance(offset, int):
        raise ValueError('M11 scroll offset invalid')
    text = (label + '   ') * 3
    pos = offset % (len(label) + 3)
    out = ''
    for ch in text[pos:]:
        if label_pixel_width(out+ch) > width:
            break
        out += ch
    return out


class MenuHistory:
    """No independent event queue; one menu generation/route owner."""
    def __init__(self, max_depth=10):
        if not 1 <= max_depth <= 16:
            raise ValueError('M11 history limit must be 1..16')
        self.max_depth = max_depth
        self.stack = []
        self.last = None
        self.scroll_anchor = None
        self.scroll_since = 0.

    def clear(self):
        self.stack.clear()
        self.last = None
        self.scroll_anchor = None
        self.scroll_since = 0.

    def entered(self, old, new, remember=True):
        if old == new:
            return
        if new == 'main':
            self.stack.clear()
        elif new in self.stack:
            # Explicit Back links (browser, temperature, settings, preview)
            # already name an ancestor. Returning must unwind that branch,
            # not push its child and create an endless Back/child loop.
            while self.stack:
                if self.stack.pop() == new:
                    break
        elif remember and old is not None:
            if len(self.stack) >= self.max_depth:
                self.stack.pop(0)
            self.stack.append(old)
        self.scroll_anchor = None

    def parent(self, current, fallback='main'):
        while self.stack:
            prev = self.stack.pop()
            if prev != current:
                self.scroll_anchor = None
                return prev
        return fallback

    def translate(self, source, language, translations):
        lang = str(language).upper()
        if lang not in LANGS:
            lang = 'EN'
        text = translations.get(source, {}).get(lang.lower(), source)
        return clean_label(text)

    def present(self, page, generation, selection, now, labels, width=216,
                interval=.2, delay=1.25):
        if not isinstance(now, (float, int)) or not math.isfinite(now):
            raise ValueError('M11 monotonic time must be finite')
        anchor = (page, generation, selection)
        if anchor != self.scroll_anchor:
            self.scroll_anchor, self.scroll_since = anchor, now
        tick = max(0, int((now-self.scroll_since-delay)/interval)) if now-self.scroll_since >= delay else 0
        return [fit_label(label, width, tick if tick and i == selection else 0)
                for i, label in enumerate(labels)]

    def check(self, rows):
        require_rows(rows)
        enabled = sum(action is not None for _, action in rows)
        return {'row_count':len(rows), 'actionable':enabled,
                'informational_or_disabled':len(rows)-enabled,
                'all_actions_known':True}


def atlas_summary(entries):
    if len(entries) != 66:
        raise ValueError('M11 stock atlas must have exactly 66 source structures')
    ram = [row.get('ram_address') for row in entries]
    if len(set(ram)) != 66:
        raise ValueError('M11 stock atlas duplicate RAM structure')
    classes = {'ADAPTED':0,'NOT_REPRODUCED':0,'UNUSED':0}
    for row in entries:
        status = row.get('historical_parity')
        if status not in classes:
            raise ValueError('M11 unknown parity qualification')
        classes[status] += 1
    if classes != {'ADAPTED':58,'NOT_REPRODUCED':3,'UNUSED':5}:
        raise ValueError('M11 stock atlas does not match audited source parity')
    return classes


def atlas_digest(entries):
    return hashlib.sha256(json.dumps(entries, sort_keys=True,
                            ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
