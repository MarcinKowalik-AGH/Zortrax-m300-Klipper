"""One production raster regardless of legacy sharp option; no hardware I/O."""
import base64
import hashlib
import zlib
import unittest
import io
from pathlib import Path
from unittest.mock import patch
from payload.m300_oem_graphics import OEMGraphics, ICON_STYLE
from payload.m300_menu_ui import M300MenuUI
from payload.m300_activity_graphics import ActivityGraphics
from test_settings_information import session

class UnifiedArtworkTests(unittest.TestCase):
    def test_default_production_ui_reports_shared_style(self):
        with session() as h:
            h.oled.menu_reverse=True
            with patch('payload.m300_menu_ui.open', return_value=io.StringIO((Path(__file__).parent/'reference/shared_artwork_atlas.json').read_text()), create=True):
                ui=M300MenuUI(h.config)
            self.assertEqual(ui.get_status(h.now)['icon_style'], 'OEM_NATIVE_TONES_V1')
            self.assertFalse(any(e[0]in('move','heat','fan')for e in h.events))

    def test_legacy_sharp_true_does_not_binarize(self):
        plain=OEMGraphics();legacy=OEMGraphics(sharp=True)
        for name in ActivityGraphics().spec['symbols']:
            for f in range(4):
                self.assertEqual(plain.get('activity:'+name,f*.5),legacy.get('activity:'+name,f*.5))

    def test_legacy_sharp_false_is_identical_to_default(self):
        plain=OEMGraphics();legacy=OEMGraphics(sharp=False)
        for addr,desc in plain.frames.items():
            for f in range(len(desc['frames'])):
                at=f*desc['period_ticks']/1000+.00001
                self.assertEqual(plain.get(addr,at),legacy.get(addr,at))

    def test_all_project_frames_retain_designed_native_tones(self):
        art=ActivityGraphics();graphics=OEMGraphics()
        for name,desc in art.spec['symbols'].items():
            for f,item in enumerate(desc['frames']):
                raw=zlib.decompress(base64.b64decode(item['zlib_b64']))
                self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
                self.assertEqual(graphics.get('activity:'+name,f*.5),(50,50,raw))
                values={v for b in raw for v in(b>>4,b&15)}
                self.assertLessEqual(values,{0,4,8,11,14,15})
                self.assertGreaterEqual(len(values),3)

    def test_oem_source_grayscale_is_not_thresholded(self):
        graphics=OEMGraphics(sharp=True);tested=0
        for addr,desc in graphics.frames.items():
            for f,item in enumerate(desc['frames']):
                at=f*desc['period_ticks']/1000+.00001
                raw=zlib.decompress(base64.b64decode(item['zlib_b64']))
                self.assertEqual(graphics.get(addr,at),(50,50,raw));tested+=1
        self.assertEqual(tested,61)

    def test_invalid_legacy_option_still_rejected(self):
        for value in('true',1,None,[]):
            with self.assertRaises(ValueError):OEMGraphics(sharp=value)

    def test_legacy_config_option_consumed_without_visual_override(self):
        for legacy in(False,True):
            with session()as h:
                h.oled.menu_reverse=True;old=h.config.getboolean
                h.config.getboolean=lambda k,d:legacy if k=='sharp_icons'else old(k,d)
                with patch('payload.m300_menu_ui.open', return_value=io.StringIO((Path(__file__).parent/'reference/shared_artwork_atlas.json').read_text()), create=True):
                    ui=M300MenuUI(h.config)
                self.assertEqual(ui.get_status(h.now)['icon_style'],ICON_STYLE)
                self.assertEqual(ui.get_status(h.now)['legacy_sharp_icons_ignored'],legacy)
                self.assertEqual(ui.oem_sprites.get('activity:bed_mesh'),OEMGraphics().get('activity:bed_mesh'))

    def test_missing_artwork_remains_read_only_and_returns_none(self):
        graphics=OEMGraphics()
        for key in('missing','activity:missing','cartesian:missing'):
            self.assertIsNone(graphics.get(key))

if __name__=='__main__':unittest.main()
