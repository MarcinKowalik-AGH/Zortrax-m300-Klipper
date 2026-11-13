"""Release integration and documentation contracts; no printer imports or I/O."""
import ast
import json
from pathlib import Path
import types
import unittest
ROOT=Path(__file__).resolve().parents[1]

class ReleaseContracts(unittest.TestCase):
    def test_four_extrusion_segments_are_the_actual_runtime_pattern(self):
        source=(ROOT/'host/klippy/extras/m300_print_control.py').read_text()
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='M300PrintControl')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_purge_lines')
        namespace={}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(ROOT),'exec'),namespace)
        owner=types.SimpleNamespace(purge_height=.28,purge_length=250.,purge_filament=20.*250/350,
                                    _error=lambda text:ValueError(text))
        for length in (40,250,350,1000):
            lines=namespace['_purge_lines'](owner,[0,0,0],[300,305,315],length)
            extrusion=[line for line in lines if line.startswith('G1 ') and ' E' in line]
            self.assertEqual(len(extrusion),4)
            self.assertEqual([line.split()[1][0] for line in extrusion],['Y','Y','X','X'])
            for line in extrusion:
                axis=line.split()[1];number=float(axis[1:])
                self.assertLessEqual(number,300 if axis[0]=='Y' else 295)
        guide=(ROOT/'docs/pl/PRINT_CONTROL.md').read_text()
        self.assertIn('2Y + 2X',guide);self.assertIn('0,28',guide)
        self.assertIn('250 mm',guide);self.assertNotIn('purge_length: 40',guide)

    def test_legacy_start_instructions_are_labeled(self):
        text=(ROOT/'docs/pl/PRINT_CONTROL_LEGACY_R16_29.md').read_text()
        self.assertIn('ARCHIWUM',text[:500]);self.assertIn('PRINT_CONTROL.md',text[:600])

    def test_publishing_still_requires_build_success(self):
        build=(ROOT/'.github/workflows/build-m300.yml').read_text()
        publish=(ROOT/'.github/workflows/publish-release.yml').read_text()
        self.assertIn('needs: build',build)
        self.assertIn("github.event.workflow_run.conclusion == 'success'",publish)
        self.assertNotIn('continue-on-error',build)
        self.assertIn('python ci/test_fluidd_selection.py',build)
        self.assertIn('python ci/test_retry_failed_workflow.py',build)
        self.assertIn('python ci/test_acceptance_register.py',build)
        self.assertIn('python docs/tools/check_manual.py',build)

    def test_current_installation_entrypoints_include_4480(self):
        for path in ('README.md','README_PL.md','docs/pl/FIRST_INSTALL.md',
                     'docs/en/FIRST_INSTALL.md','docs/en/INSTALL.md','docs/pl/USER_GUIDE.md'):
            text=(ROOT/path).read_text()
            self.assertIn('4480',text,path)
            for line in text.splitlines():
                if line.strip().startswith(('python3 ','python ')) and 'install-orange-pi.py' in line:
                    self.assertIn('--port 4480',line,path)
        for lang in ('pl','en'):
            text=(ROOT/'docs'/lang/'FIRST_INSTALL.md').read_text()
            self.assertIn('releases/download/v1.0.0-rc.7/',text)

    def test_host_release_and_numeric_mcu_identity(self):
        meta=json.loads((ROOT/'PORT.json').read_text())
        self.assertEqual(meta['distribution_version'],'v1.0.0-rc.7')
        self.assertEqual(meta['mcu_release'],'1.0.3')
        self.assertEqual(meta['self_contained_host_tests'],896)
        self.assertEqual(meta['print_control_revision'],'0.13.16.38-PRINT-DRAIN-XY-PURGE')

if __name__=='__main__':unittest.main(verbosity=2)
