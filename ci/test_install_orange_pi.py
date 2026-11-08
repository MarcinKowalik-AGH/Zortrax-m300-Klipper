"""Validate the deployment helper without changing a real web root or service."""
from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import install_orange_pi as installer


class OrangePiInstallerTest(unittest.TestCase):
    def test_repair_accepts_only_current_known_crash_and_exact_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'klippy/extras/m300_native_maintenance.py'
            target.parent.mkdir(parents=True);target.write_text('known-broken-runtime')
            log=root/'klippy.log'
            trace=("Start printer at now\nTraceback\n  File '/home/me/klipper/klippy/extras/m300_native_maintenance.py', line 449\n"
                   "AttributeError: 'M300NativeMaintenance' object has no attribute 'hotend'\n")
            log.write_text(trace)
            info=dict(state='shutdown',state_message='Unhandled exception during run',
                      klipper_path=str(root),log_file=str(log))
            sha=hashlib.sha256(target.read_bytes()).hexdigest()
            with patch.object(installer,'BUGGY_MAINTENANCE_SHA256',sha):
                self.assertTrue(installer.startup_status_failure(info))
                with patch.object(installer,'printer',return_value=info) as query:
                    self.assertEqual(installer.require_idle(repair_startup=True),info)
                    query.assert_called_once_with('/printer/info')
                with patch.object(installer,'printer',return_value=info):
                    with self.assertRaisesRegex(ValueError,'Ready'):installer.require_idle()
                for state,reason in (('shutdown','M300 local guard latched'),('error','Unknown config option'),
                        ('ready',''),('shutdown','MCU ADC out of range')):
                    self.assertFalse(installer.startup_status_failure(dict(info,state=state,state_message=reason)))
                log.write_text(trace+'Start printer at later\nMCU ADC out of range\n')
                self.assertFalse(installer.startup_status_failure(info))
                log.write_text(trace);target.write_text('custom-runtime')
                self.assertFalse(installer.startup_status_failure(info))

    def test_startup_repair_does_not_accept_unknown_shutdown_or_active_print(self):
        with patch.object(installer,'startup_status_failure',return_value=False):
            with patch.object(installer,'printer',return_value=dict(state='shutdown',state_message='M112')):
                with self.assertRaisesRegex(ValueError,'exact early-status'):installer.require_idle(repair_startup=True)
        for state in ('printing','paused'):
            with patch.object(installer,'printer',side_effect=[dict(state='ready'),dict(status=dict(print_stats=dict(state=state)))]):
                with self.assertRaisesRegex(ValueError,'idle'):installer.require_idle(repair_startup=True)

    def test_verified_repair_restarts_host_without_resetting_mcu(self):
        with patch.object(installer,'require_idle',return_value=dict(state='shutdown')) as idle:
            with patch.object(installer,'run') as run:
                installer.apply_host(Path('/package/host'),('--root','/my/klipper','--config','/my/printer.cfg'),
                    dict(status='PLAN_M300_R16_12'),repair_startup=True)
        idle.assert_called_once_with(repair_startup=True)
        calls=[c.args for c in run.call_args_list]
        self.assertEqual(calls[0],('sudo','systemctl','stop','klipper.service'))
        self.assertEqual(calls[-1],('sudo','systemctl','start','klipper.service'))
        self.assertEqual(len(calls),3)
        self.assertIn('--apply',calls[1])

    def test_known_pad_config_error_can_install_without_unavailable_print_stats(self):
        info={'state':'error','state_message':installer.OLD_PAD_GEOMETRY_ERROR}
        with patch.object(installer,'printer',return_value=info) as printer:
            self.assertEqual(installer.require_idle(),info)
        printer.assert_called_once_with('/printer/info')

    def test_config_recovery_never_accepts_runtime_shutdown_or_unrelated_startup_errors(self):
        for state,message in (('shutdown',installer.OLD_PAD_GEOMETRY_ERROR),
                ('startup',installer.OLD_PAD_GEOMETRY_ERROR),('error','MCU connection failed')):
            with self.subTest(state=state,message=message):
                with patch.object(installer,'printer',return_value={'state':state,'state_message':message}) as printer:
                    with self.assertRaisesRegex(ValueError,'Ready'):installer.require_idle()
                printer.assert_called_once_with('/printer/info')

    def test_installation_still_refuses_printing_or_paused_ready_host(self):
        for state in ('printing','paused'):
            with self.subTest(state=state),patch.object(installer,'run') as run:
                with patch.object(installer,'printer',side_effect=[{'state':'ready'},
                        {'status':{'print_stats':{'state':state}}}]):
                    with self.assertRaisesRegex(ValueError,'idle'):
                        installer.apply_host(Path('/package/host'),(),{'status':'PLAN_M300_R16_12'})
                run.assert_not_called()

    def test_nginx_port_selects_fluidd(self):
        config = '''
            http {
                server { listen 80; root /var/www/default; }
                server {
                    listen 192.168.4.157:4080 default_server;
                    listen [::]:4080;
                    root "/home/klipper/fluidd";
                    location / { try_files $uri $uri/ /index.html; }
                    location /websocket { proxy_pass http://moonraker; }
                }
            }
        '''
        self.assertEqual(installer.nginx_root(config, 4080), Path('/home/klipper/fluidd'))

    def test_ambiguous_or_missing_web_root_is_refused(self):
        config = '''
            server { listen 4080; root /var/www/fluidd; }
            server { listen 4080; root /var/www/other; }
        '''
        for port in (80, 4080):
            with self.assertRaises(ValueError):
                installer.nginx_root(config, port)

    def test_installed_host_skips_service_restart(self):
        with patch.object(installer, 'run') as run:
            installer.apply_host(Path('/package/host'), (), {'status': 'ALREADY_M300_R16_12'})
        run.assert_not_called()

    def test_web_update_preserves_config_and_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            backup = installer.deploy_web(source, root, 'new', execute=self.local_run)
            self.assertEqual((backup / 'index.html').read_text(), 'old')
            self.assertEqual((root / 'index.html').read_text(), 'new')
            self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
            with patch.object(installer, 'run') as run:
                self.assertIsNone(installer.deploy_web(source, root, 'new', execute=run))
            run.assert_not_called()

    def test_failed_nginx_reload_restores_web_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))

            def fail_reload(sudo, *args, **kwargs):
                if args[0] == 'systemctl':
                    raise subprocess.CalledProcessError(1, args)
                return self.local_run(sudo, *args, **kwargs)

            with self.assertRaises(subprocess.CalledProcessError):
                installer.deploy_web(source, root, 'new', execute=fail_reload)
            self.assertEqual((root / 'index.html').read_text(), 'old')
            self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['new', 'web'])

    @staticmethod
    def web_paths(parent):
        source, root = parent / 'new', parent / 'web'
        source.mkdir()
        root.mkdir()
        (source / '.m300-fluidd-build').write_text('new\n')
        (source / 'index.html').write_text('new')
        (root / 'index.html').write_text('old')
        (root / 'config.json').write_text('{"custom":true}')
        return source, root

    @staticmethod
    def local_run(sudo, *args, **kwargs):
        if args[0] not in ('systemctl', 'chown'):
            return installer.run(*args, **kwargs)


if __name__ == '__main__':
    unittest.main()
