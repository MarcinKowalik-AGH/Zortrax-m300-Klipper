# SPDX-License-Identifier: GPL-3.0-or-later
"""Adapted 5x7/5x8 supplemental glyphs for five classic-M300 languages.

Not extracted stock 13-pixel glyphs. Existing ASCII+Polish base glyphs remain
untouched so previously qualified framebuffer/golden images are unchanged.
"""
ACCENTS = {
    'acute': [2,4,0,0,0], 'grave':[8,4,0,0,0],
    'circumflex':[4,10,17,0,0], 'diaeresis':[10,10,0,0,0],
    'tilde':[9,22,0,0,0],
}
COMPOSE = {
    'É':('E','acute'), 'é':('e','acute'), 'è':('e','grave'),
    'ê':('e','circumflex'), 'à':('a','grave'), 'â':('a','circumflex'),
    'ô':('o','circumflex'), 'û':('u','circumflex'),
    'Ü':('U','diaeresis'), 'ü':('u','diaeresis'),
    'ä':('a','diaeresis'), 'ö':('o','diaeresis'),
    'á':('a','acute'), 'í':('i','acute'), 'ú':('u','acute'),
    'ñ':('n','tilde'), 'Ñ':('N','tilde'),
    'ç':('c','grave'), 'Ç':('C','grave'),
    'Á':('A','acute'), 'Í':('I','acute'), 'Ú':('U','acute'),
}
EXTRA = {
    'ß':[30,17,17,30,17,17,30],
    '’':[4,4,8,0,0,0,0],
    '¿':[0,4,0,4,8,17,14],
    '\u20ac':[7,8,30,8,30,8,7],
    '\u00a0':[0]*7,
    '\u2013':[0,0,0,31,0,0,0],
    '\u2014':[0,0,0,31,0,0,0],
}


def supplemental(base):
    result = {key:tuple(value) for key,value in EXTRA.items()}
    for char, (base_char, kind) in COMPOSE.items():
        rows = list(base[base_char]); mark = list(ACCENTS[kind]);
        # Preserve the shape of base 5x7, render a separate accent row above.
        accent_row = mark[0] | mark[1] | mark[2]
        result[char] = tuple([accent_row] + rows)
    return result
