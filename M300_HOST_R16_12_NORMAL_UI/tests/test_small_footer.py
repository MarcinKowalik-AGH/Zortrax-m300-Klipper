"""The footer must retain suffixes clipped by the native 16-character LCD."""
import unittest

import test_display  # Install the checksum-pinned generic render fixture.
from payload import m300_status_footer as renderer

class SmallFooterTests(unittest.TestCase):
    def test_mesh_phase_suffix_survives_the_original_sixteen_character_limit(self):
        message = 'Bed mesh: Heating nozzle / bed'
        wire = renderer.klipper_footer(message)
        self.assertEqual(len(wire), 16*128)
        self.assertNotEqual(wire, renderer.klipper_footer(message[:16]))
        self.assertTrue(any(value for row in range(4,11) for value in wire[row*128+82:row*128+95]))
        self.assertTrue(any(value for row in range(4,11) for value in wire[row*128+48:row*128+90]))

    def test_long_notice_uses_both_rows_and_keeps_the_last_row_inside_the_panel(self):
        message = 'Bed mesh: Heating nozzle and bed before homing; please wait for stable temperatures'
        wire = renderer.klipper_footer(message)
        self.assertTrue(any(wire[:7*128]))
        self.assertTrue(any(wire[8*128:15*128]))
        self.assertFalse(any(wire[7*128:8*128]))
        self.assertFalse(any(wire[15*128:16*128]))
        self.assertEqual(renderer.klipper_footer(''), bytes(16*128))

    def test_cached_footer_changes_when_only_the_message_suffix_changes(self):
        a = 'Bed mesh: Measuring point 11 of 25'
        b = 'Bed mesh: Measuring point 12 of 25'
        self.assertEqual(a[:16],b[:16])
        self.assertNotEqual(renderer.klipper_footer(a),renderer.klipper_footer(b))
        self.assertEqual(renderer.klipper_footer('Ready ~degrees~'),renderer.klipper_footer('Ready °'))
