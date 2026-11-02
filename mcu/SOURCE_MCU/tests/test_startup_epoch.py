"""Cold start through the real generic timer initialization, without host config."""
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PIN='ee2c6fb6b00b2b5d097ef70d0868df7d74943b51'

def generic_init_source():
    with zipfile.ZipFile(ROOT/'UPSTREAM_KLIPPER_PINNED.zip') as z:
        source=z.read('klipper-'+PIN+'/src/generic/armcm_timer.c').decode()
    start=source.index('void\ntimer_init(void)\n{');end=source.index('\nDECL_INIT(timer_init);',start)
    return source[start:end]+'\n'

class StartupEpoch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='m300-startup-')
        root=Path(cls.temp.name);cls.binary=root/'startup'
        generic=root/'generic_init.c';generic.write_text(generic_init_source())
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-DM300_GENERIC_TIMER_INIT_FILE="'+str(generic)+'"',
            str(ROOT/'tests/test_startup_epoch.c'),'-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def run_case(self,**values):
        env=os.environ.copy();env.update({k:str(v)for k,v in values.items()})
        r=subprocess.run([str(self.binary)],env=env,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return json.loads(r.stdout)

    def test_zero_and_inherited_counters_all_saved_baud_rates(self):
        times=[]
        for inherited in [0,1,864000000,1728000000,0x7ffff000,0x80000000,0xfffff000,0xffffffff]:
            for baud in [19200,57600,115200,250000,500000,750000,1000000,1500000]:
                with self.subTest(inherited=inherited,baud=baud):
                    r=self.run_case(M300_INHERITED_CLOCK=inherited,M300_BAUD=baud)
                    self.assertEqual(r['ready'],1)
                    self.assertLess(r['ready_at_us'],1000000)
                    self.assertGreaterEqual(r['ready_at_us'],530000)
                    times.append(r['ready_at_us'])
        self.assertEqual(len(set(times)),1) # no inherited epoch changes the start

    def test_host_handover_at_every_startup_phase(self):
        for at in [0,1000,10000,500000,530000,560000,700000,1000000]:
            with self.subTest(at=at):
                self.assertEqual(self.run_case(M300_HOST_AT_US=at)['host'],1)

    def test_shutdown_before_first_task_and_during_drawing(self):
        for at in [0,1000,10000,530000,560000,700000,1000000]:
            with self.subTest(at=at):
                self.assertEqual(self.run_case(M300_SHUTDOWN_AT_US=at)['shutdown'],1)

    def test_early_host_config_keeps_its_spi_clock(self):
        r=self.run_case(M300_EARLY_CONFIG=1)
        self.assertEqual(r['ready'],1)

    def test_full_wire_matches_independent_font_oracle_at_every_baud(self):
        source=(ROOT/'overlay/src/stm32/m300_oled_stock_glyphs.inc').read_text()
        def numbers(name):
            body=re.search(name+r'\[[^\]]*\]\s*=\s*\{(.*?)\}',source,re.S)[1]
            return [int(x.strip(),0) for x in body.split(',') if x.strip()]
        packed,spans=numbers('glyph_packed'),numbers('glyph_span')
        glyphs={};at=0
        for code in range(32,127):
            h=packed[at];at+=1;width=h>>4;span=h&15
            if span==15:span=packed[at];at+=1
            else:span=spans[span]
            size=(width*(span&15)+7)//8
            glyphs[chr(code)]=(width,span,packed[at:at+size]);at+=size
        for baud in [19200,57600,115200,250000,500000,750000,1000000,1500000]:
            screen=[[0]*256 for _ in range(64)]
            for x in range(4,252):screen[12][x]=5
            for y,text in [(2,'ZORTRAX M300'),(18,'Waiting for Klipper...'),
                           (34,'MCU: 0.13.14.4 U8'),(50,f'UART: {baud} 8N1')]:
                x=4
                for char in text:
                    w,span,bits=glyphs[char]
                    if x+w>252:break
                    for row in range(span&15):
                        py=y+(span>>4)+row-3
                        for col in range(w):
                            bit=row*w+col
                            if 0<=py<64 and bits[bit//8]&(1<<(bit%8)):screen[py][x+col]=15
                    x+=w+1
            expected=bytes((row[x]<<4)|row[x+1] for row in screen for x in range(0,256,2))
            out=Path(self.temp.name)/f'{baud}.bin'
            self.run_case(M300_BAUD=baud,M300_FRAME_OUTPUT=out)
            self.assertEqual(out.read_bytes(),expected)

if __name__=='__main__':unittest.main()
