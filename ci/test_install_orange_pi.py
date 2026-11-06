"""Validate the deployment helper without changing a real web root or service."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import install_orange_pi as installer


class OrangePiInstallerTest(unittest.TestCase):
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
