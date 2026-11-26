"""Public first-install package integrity and current-deployment selection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('bootstrap',Path(__file__).resolve().parents[1]/'install-new-host.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base=Path(self.temporary.name)
        self.archive=self.base/'base.zip'
        provenance=json.dumps(dict(model='M300_CLASSIC',release_stage='VERIFIED',
            upstream_commit='a'*40,github_commit='b'*40))
        self.old={'BUILD_PROVENANCE.json':provenance,'M300_HOST/old.txt':'old',
            'FIRST_INSTALL/old.cfg':'old','MCU/old.dict':'old',
            'KLIPPER_HOST/klippy/gcode.py':'base parser',
            'KLIPPER_HOST/klippy/extras/base_compat.py':'retain static API'}
        self.write_archive(self.old)
        self.current=self.base/'current';self.current.mkdir()
        latest=dict(model='M300_CLASSIC',release_stage='VERIFIED',
                    upstream_commit='a'*40,github_commit='c'*40)
        self.files={'BUILD_PROVENANCE.json':json.dumps(latest),
            'install-fresh.py':'new installer','install-orange-pi.py':'updater',
            'install-new-host.py':'bootstrap','M300_FLUIDD.zip':'new frontend',
            'install-camera.py':'optional camera installer','CAMERA_PL.md':'camera instructions',
            'CAMERA_EN.md':'camera instructions',
            'read-host-temperatures.py':'read-only thermal diagnostic',
            'HOST_TEMPERATURE_PL.md':'temperature instructions',
            'HOST_TEMPERATURE_EN.md':'temperature instructions',
            'MCU/klipper.dict':'new dictionary',
            'FIRST_INSTALL/m300_classic_base.cfg':'public base config',
            'FIRST_INSTALL/m300_classic_services.cfg':'public services',
            'FIRST_INSTALL/m300_classic_sensors.cfg':'public sensors',
            'FIRST_INSTALL/requirements-m300.txt':'exact requirements',
            'FIRST_INSTALL/m300_camera.conf':'[camera]\nenabled: False\n',
            'FIRST_INSTALL/m300_host_temperature.cfg':'[temperature_sensor Host]\n',
            'FIRST_INSTALL/m300_mcu_temperature.cfg':'[m300_mcu_temperature]\n',
            'M300_HOST/core/gcode.py':'current parser',
            'M300_HOST/payload/m300_mcu_temperature.py':'current MCU diagnostic',
            'M300_HOST/payload/m300_current.py':'current module'}
        self.write_current()

    def write_archive(self,files,extra=None):
        with zipfile.ZipFile(self.archive,'w') as archive:
            values=dict(files)
            values['SHA256SUMS']=''.join(__import__('hashlib').sha256(text.encode()).hexdigest()
                +'  '+name+'\n' for name,text in files.items())
            for name,text in values.items():
                archive.writestr(bootstrap.BASE_NAME+'/'+name,text)
            if extra:
                archive.writestr(extra,'unsafe')

    def write_current(self):
        for name,text in self.files.items():
            target=self.current/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        (self.current/'SHA256SUMS').write_text(''.join(bootstrap.digest(self.current/name)+'  '+name+'\n'
            for name in self.files))

    def test_current_modules_config_frontend_and_dictionary_replace_base(self):
        result=bootstrap.compose_package(self.archive,self.current,self.base/'out')
        self.assertEqual((result/'KLIPPER_HOST/klippy/extras/m300_current.py').read_text(),'current module')
        self.assertEqual((result/'KLIPPER_HOST/klippy/gcode.py').read_text(),'current parser')
        self.assertEqual((result/'KLIPPER_HOST/klippy/extras/base_compat.py').read_text(),'retain static API')
        self.assertEqual((result/'M300_FLUIDD.zip').read_text(),'new frontend')
        self.assertEqual((result/'MCU/klipper.dict').read_text(),'new dictionary')
        self.assertEqual((result/'FIRST_INSTALL/m300_classic_base.cfg').read_text(),'public base config')
        self.assertFalse((result/'FIRST_INSTALL/old.cfg').exists())
        self.assertEqual((result/'install-camera.py').read_text(),'optional camera installer')
        self.assertIn('enabled: False', (result/'FIRST_INSTALL/m300_camera.conf').read_text())
        self.assertEqual((result/'KLIPPER_HOST/klippy/extras/m300_mcu_temperature.py').read_text(),
                         'current MCU diagnostic')
        self.assertTrue((result/'FIRST_INSTALL/m300_host_temperature.cfg').is_file())
        self.assertTrue((result/'FIRST_INSTALL/m300_mcu_temperature.cfg').is_file())
        self.assertTrue((result/'read-host-temperatures.py').is_file())
        self.assertEqual(json.loads((result/'BOOTSTRAP_PROVENANCE.json').read_text())['deployment_commit'],'c'*40)
        bootstrap.manifest(result)

    def test_modified_payload_is_rejected_before_unpacking(self):
        (self.current/'M300_HOST/payload/m300_current.py').write_text('unexpected local change')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):
            bootstrap.compose_package(self.archive,self.current,self.base/'out')
        self.assertFalse((self.base/'out').exists())

    def test_unpublished_old_deployment_cannot_install_an_empty_config(self):
        self.files.pop('install-fresh.py');self.write_current()
        with self.assertRaisesRegex(ValueError,'lacks the new-host installer'):
            bootstrap.compose_package(self.archive,self.current,self.base/'out')

    def test_foreign_core_is_not_mixed_with_m300_payload(self):
        doc=json.loads(self.files['BUILD_PROVENANCE.json']);doc['upstream_commit']='d'*40
        self.files['BUILD_PROVENANCE.json']=json.dumps(doc);self.write_current()
        with self.assertRaisesRegex(ValueError,'different verified Klipper core'):
            bootstrap.compose_package(self.archive,self.current,self.base/'out')

    def test_zip_path_traversal_is_rejected(self):
        self.write_archive(self.old,bootstrap.BASE_NAME+'/../../outside')
        with self.assertRaisesRegex(ValueError,'Unsafe base release'):
            bootstrap.compose_package(self.archive,self.current,self.base/'out')
        self.assertFalse((self.base/'outside').exists())

    def test_cached_release_is_hash_checked_without_network(self):
        cache=self.base/'cache';cache.mkdir()
        (cache/(bootstrap.BASE_NAME+'.zip')).write_text('not a release')
        with patch.object(bootstrap.urllib.request,'urlopen') as network:
            with self.assertRaisesRegex(ValueError,'Invalid cached release'):
                bootstrap.download_base(cache)
            network.assert_not_called()


if __name__=='__main__':
    unittest.main(verbosity=2)
