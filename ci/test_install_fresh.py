"""First-install data migration and rollback; never invokes system services."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import install_fresh as fresh
from project import ROOT, manifest, stage_host_update


class FirstInstallTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base=Path(self.temp.name)
        self.root=self.base/'klipper';(self.root/'klippy/extras').mkdir(parents=True)
        (self.root/'klippy/klippy.py').write_text('stock')
        self.data=self.base/'printer_data';(self.data/'config').mkdir(parents=True)
        self.config=self.data/'config/printer.cfg'
        self.config.write_text('[include fluidd.cfg]\n')
        self.moon=self.data/'config/moonraker.conf'
        self.moon.write_text('[server]\nhost: 0.0.0.0\n[authorization]\ntrusted_clients: 127.0.0.1\n'
            '[update_manager klipper]\norigin: https://github.com/Klipper3d/klipper.git\n'
            '[update_manager fluidd]\nrepo: fluidd-core/fluidd\n')
        self.package=self.base/'package';self.package.mkdir()
        first=self.package/'FIRST_INSTALL';first.mkdir()
        for name in ('m300_classic_base.cfg','m300_classic_services.cfg','m300_classic_sensors.cfg'):
            shutil.copy2(ROOT/'host/config'/name,first/name)
        (first/'requirements-m300.txt').write_text('cffi==2.1.1\n')
        stage_host_update(self.package/'M300_HOST')
        (self.package/'BUILD_PROVENANCE.json').write_text(json.dumps(dict(
            model='M300_CLASSIC',release_stage='VERIFIED',github_commit='a'*40)))
        shutil.copy2(ROOT/'ci/install_orange_pi.py',self.package/'install-orange-pi.py')
        self.web=self.base/'web';self.web.mkdir();(self.web/'index.html').write_text('<title>fluidd</title>old')
        (self.web/'config.json').write_text('{"custom":true}')
        with zipfile.ZipFile(self.package/'M300_FLUIDD.zip','w') as z:
            z.writestr('fluidd-m300/index.html','<title>fluidd</title>new')

    def tearDown(self):self.temp.cleanup()

    def test_existing_printer_never_overwritten(self):
        for content in ('[stepper_x]\nstep_pin: PB3\n','[printer]\nkinematics: cartesian\n',
                        '#*# SAVE_CONFIG\n','[gcode_macro PAUSE]\ngcode: M112\n'):
            with self.subTest(content=content):
                self.config.write_text(content)
                with self.assertRaises(ValueError):fresh.refuse_existing(self.config,self.root)
                self.assertEqual(self.config.read_text(),content)

    def test_existing_m300_requires_updater(self):
        (self.root/'klippy/extras/m300_mcu.py').write_text('existing')
        with self.assertRaisesRegex(ValueError,'already installed'):fresh.refuse_existing(self.config,self.root)

    def test_actual_kiauh_placeholder_is_accepted_real_mcu_is_refused(self):
        text='[mcu]\nserial: /dev/serial/by-id/<your-mcu-id>\n\n[virtual_sdcard]\npath: '+str(self.data/'gcodes')+'\non_error_gcode: CANCEL_PRINT\n\n[printer]\nkinematics: none\nmax_velocity: 1000\nmax_accel: 1000\n'
        self.config.write_text(text)
        fresh.refuse_existing(self.config,self.root)
        self.config.write_text(text.replace('/dev/serial/by-id/<your-mcu-id>','/dev/ttyUSB0'))
        with self.assertRaises(ValueError):fresh.refuse_existing(self.config,self.root)

    def test_kiauh_shell_allowed_but_existing_state_is_not(self):
        fresh.refuse_existing(self.config,self.root)
        (self.config.parent/'m300_settings.json').write_text('keep')
        with self.assertRaisesRegex(ValueError,'Existing printer data'):fresh.refuse_existing(self.config,self.root)

    def test_release_checksum_checked_before_importing_runtime(self):
        runtime=self.package/'KLIPPER_HOST/klippy';runtime.mkdir(parents=True)
        (runtime/'klippy.py').write_text('never execute')
        values={str(p.relative_to(self.package)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.package.rglob('*') if p.is_file()}
        (self.package/'SHA256SUMS').write_text(''.join(v+'  '+p+'\n' for p,v in values.items()))
        self.assertEqual(fresh.verify(self.package)['model'],'M300_CLASSIC')
        (runtime/'klippy.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):fresh.verify(self.package)

    def test_render_paths_geometry_and_no_ci_or_legacy_state(self):
        out=self.base/'out';out.mkdir()
        fresh.render_config(self.package,out,self.data,Path('/dev/serial0'),750000,'M300_TEST_ID')
        text='\n'.join(p.read_text() for p in out.iterdir())
        self.assertNotIn('/home/klipper',text)
        self.assertNotIn('TEST01',text)
        self.assertNotIn('@DATA@',text)
        self.assertNotIn('force_move',text)
        self.assertNotIn('m300_ci_',text)
        self.assertIn('serial: /dev/serial0',text)
        self.assertIn('baud: 750000',text)
        self.assertIn('park_y: 305',text)
        self.assertIn('z_home_hotend_target: 180',text)
        self.assertIn('max_bed_span: 0.8',text)

    def test_exact_stock_updaters_removed_custom_auth_retained(self):
        text=fresh.moonraker_config(self.moon.read_text()+'\n[update_manager camera]\norigin: https://example.org/camera\n')
        self.assertNotIn('update_manager klipper',text)
        self.assertNotIn('update_manager fluidd',text)
        self.assertIn('trusted_clients: 127.0.0.1',text)
        self.assertIn('update_manager camera',text)
        with self.assertRaisesRegex(ValueError,'Custom updater'):
            fresh.moonraker_config('[update_manager klipper]\norigin: https://example.org/fork\n')

    def test_standard_kiauh_environment_service_is_recognized(self):
        (self.data/'systemd').mkdir()
        env=self.data/'systemd/klipper.env'
        env.write_text('KLIPPER_ARGS="'+str(self.root/'klippy/klippy.py')+' '+str(self.config)+' -a '+str(self.data/'comms/klippy.sock')+'"\n')
        python=self.base/'klippy-env/bin/python'
        def command(*args,**kw):
            return 'test-user\n' if args[0]=='id' else 'User=test-user\nExecStart='+str(python)+' $KLIPPER_ARGS\nEnvironmentFiles='+str(env)+' (ignore_errors=no)\n'
        with patch.object(fresh,'run',side_effect=command):fresh.check_service(self.data,self.root,python)

    def test_foreign_service_socket_refused(self):
        with patch.object(fresh,'run',side_effect=['User=me\nExecStart=/python /other/klippy.py\n','me\n']):
            with self.assertRaises(ValueError):fresh.check_service(self.data,self.root,Path('/python'))

    def test_apply_replaces_only_empty_setup_and_keeps_backup(self):
        self.prepare_runtime()
        calls=[]
        backup=fresh.install(self.package,self.root,self.data,Path('/python'),Path('/dev/ttyS1'),750000,
                             self.web,execute=lambda *a,**kw:self.execute(calls,*a,**kw))
        self.assertEqual((backup/'klipper/klippy/klippy.py').read_text(),'stock')
        self.assertEqual((backup/'printer.cfg').read_text(),'[include fluidd.cfg]\n')
        self.assertIn('park_x: 300',(self.config.parent/'m300_services.cfg').read_text())
        self.assertIn('new',(self.web/'index.html').read_text())
        self.assertEqual((self.web/'config.json').read_text(),'{"custom":true}')
        self.assertFalse(any(a and a[0] in ('G28','M104','M140','FIRMWARE_RESTART') for a in calls))
        self.assertNotIn('update_manager klipper',self.moon.read_text())

    def test_failed_web_deploy_restores_entire_previous_setup(self):
        self.prepare_runtime();old_moon=self.moon.read_text();calls=[]
        def execute(*a,**kw):
            if a[:4]==('sudo','systemctl','reload','nginx'):raise subprocess.CalledProcessError(1,a)
            return self.execute(calls,*a,**kw)
        with self.assertRaises(subprocess.CalledProcessError):
            fresh.install(self.package,self.root,self.data,Path('/python'),Path('/dev/ttyS1'),750000,self.web,execute=execute)
        self.assertEqual((self.root/'klippy/klippy.py').read_text(),'stock')
        self.assertEqual(self.config.read_text(),'[include fluidd.cfg]\n')
        self.assertEqual(self.moon.read_text(),old_moon)
        self.assertFalse((self.config.parent/'m300_services.cfg').exists())
        self.assertIn('old',(self.web/'index.html').read_text())

    def prepare_runtime(self):
        # Copy pristine core + current overlay, exactly as release packaging does.
        shutil.copytree(ROOT/'.ci/pristine',self.package/'KLIPPER_HOST',
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.so'))
        shutil.copytree(ROOT/'host/klippy',self.package/'KLIPPER_HOST/klippy',dirs_exist_ok=True)

    @staticmethod
    def execute(calls,*args,**kw):
        calls.append(args)
        if str(args[0])!='/python' and not (args[0]=='sudo' and args[1] in ('systemctl','chown')):
            if args[0]=='sudo':args=args[1:]
            return fresh.run(*args,**kw)


if __name__=='__main__':unittest.main()
