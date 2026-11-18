"""Validate the deployment helper without changing a real web root or service."""
from contextlib import contextmanager
from pathlib import Path
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import stat
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

import install_orange_pi as installer


class QuietHTTPHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


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
            with patch.object(installer,'run',return_value=self.applied_host()) as run:
                installer.apply_host(Path('/package/host'),('--root','/my/klipper','--config','/my/printer.cfg'),
                    dict(status='PLAN_M300_HOST'),repair_startup=True)
        idle.assert_called_once_with(repair_startup=True, recover_counter_startup=False)
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
                        installer.apply_host(Path('/package/host'),(),{'status':'PLAN_M300_HOST'})
                run.assert_not_called()

    def test_terminal_print_stats_still_require_motion_services_and_heaters_idle(self):
        status = {'print_stats': {'state': 'cancelled'}, 'pause_resume': {'is_paused': False},
                  'idle_timeout': {'state': 'Ready'}, 'extruder': {'target': 0},
                  'heater_bed': {'target': 0},
                  'toolhead': {'print_time': 10, 'estimated_print_time': 11}}
        info = {'state': 'ready'}
        with patch.object(installer, 'printer', side_effect=[info, {'status': status}]) as printer:
            self.assertEqual(installer.require_idle(), info)
            self.assertEqual(printer.call_args.args, (installer.IDLE_QUERY,))
        for name, state in (('m300_print_control', {'busy': True}),
                            ('m300_print_control', {'paused': True}),
                            ('m300_maintenance', {'busy': True}),
                            ('pause_resume', {'is_paused': True}),
                            ('idle_timeout', {'state': 'Printing'}),
                            ('toolhead', {'print_time': 12, 'estimated_print_time': 11}),
                            ('toolhead', {'print_time': float('nan'), 'estimated_print_time': 11}),
                            ('heater_bed', {'target': 100})):
            with self.subTest(name=name), patch.object(installer, 'printer', side_effect=[
                    info, {'status': dict(status, **{name: state})}]):
                with self.assertRaisesRegex(ValueError, 'idle'):
                    installer.require_idle()

    def test_counter_startup_repair_requires_live_preconnect_failure(self):
        message = "Unable to obtain 'm300_factory_counter_result' response"
        info = dict(state='shutdown', state_message="Previous MCU 'mcu' shutdown: M300 local guard latched")
        hardware = dict(factory_counter_pending=True, factory_counter_sync='RECOVERY_REQUIRED',
                        factory_counter_error=message)
        board = dict(ready=False, identified=False, connected=False, native_initialization='NOT_STARTED',
                     hardware=hardware)
        status = dict(m300_mcu=board, m300_lifecycle=dict(startup_reconnect=dict(decision='NOT_CHECKED')))
        with patch.object(installer, 'printer', side_effect=[info, dict(status=status)]):
            self.assertEqual(installer.require_idle(recover_counter_startup=True), info)
        for changed in ({'connected': True}, {'ready': True}, {'hardware': {}},
                        {'hardware': dict(hardware, factory_counter_error='another failure')}):
            with patch.object(installer, 'printer', side_effect=[
                    info, dict(status=dict(status, m300_mcu=dict(board, **changed)))]):
                with self.assertRaises(ValueError):
                    installer.require_idle(recover_counter_startup=True)
        with patch.object(installer, 'printer', return_value=info) as query:
            with self.assertRaises(ValueError):
                installer.require_idle()
            query.assert_called_once_with('/printer/info')
        with patch.object(installer, 'printer', return_value=dict(info, state_message='MCU ADC out of range')):
            with self.assertRaises(ValueError):
                installer.require_idle(recover_counter_startup=True)

    def test_unready_host_restores_receipt_and_restarts_prior_services(self):
        with patch.object(installer, 'require_idle'), \
             patch.object(installer, 'wait_ready', side_effect=ValueError('MCU startup failed')), \
             patch.object(installer, 'run', return_value=self.applied_host()) as run:
            with self.assertRaisesRegex(ValueError, 'MCU startup failed'):
                installer.apply_host(Path('/package/host'), (), {
                    'status': 'PLAN_M300_HOST', 'files': ['/config/moonraker.conf']})
        operations = [call.args[2:] for call in run.call_args_list]
        self.assertEqual(operations, [
            ('stop', 'klipper.service'), ('--apply',), ('start', 'klipper.service'),
            ('restart', 'moonraker.service'), ('stop', 'klipper.service'),
            ('--rollback', '/previous/RECEIPT.json'), ('start', 'klipper.service'),
            ('restart', 'moonraker.service')])

    @staticmethod
    def applied_host():
        return json.dumps(dict(status='INSTALLED_M300_HOST', receipt='/previous/RECEIPT.json'))

    def test_qualified_geometry_flag_reaches_host_plan(self):
        self.check_geometry_flag(True)

    def test_normal_update_does_not_select_qualified_geometry(self):
        self.check_geometry_flag(False)

    def test_default_update_never_checks_or_changes_fluidd(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / 'SHA256SUMS').touch()
            info = {'klipper_path': '/home/klipper/klipper', 'config_file': '/config/printer.cfg'}
            plan = {'status': 'PLAN_M300_HOST', 'host_update': '1.0.0-rc.11'}
            with patch.object(installer, 'PACKAGE', package), \
                 patch.object(installer.os, 'geteuid', return_value=1000), \
                 patch.object(sys, 'argv', ['install-orange-pi.py', '--port', '4480']), \
                 patch.object(installer, 'require_idle', return_value=info), \
                 patch.object(installer, 'apply_host', return_value='/receipt.json') as apply, \
                 patch.object(installer, 'update_fluidd') as web, \
                 patch.object(installer, 'run', return_value=json.dumps(plan)) as run, \
                 patch('builtins.print') as report:
                installer.main()
            web.assert_not_called()
            apply.assert_called_once_with(package / 'M300_HOST', (
                '--root', info['klipper_path'], '--config', info['config_file']),
                plan, repair_startup=False, recover_counter_startup=False)
            self.assertEqual([call.args[:2] for call in run.call_args_list],
                             [('sha256sum', '-c'), (sys.executable, 'install.py'), ('sudo', '-v')])
            self.assertEqual(json.loads(report.call_args.args[0]), {
                'status': 'INSTALLED_M300_HOST', 'host_update': '1.0.0-rc.11',
                'host_receipt': '/receipt.json', 'mcu_flashed': False})

    def test_explicit_fluidd_update_is_web_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            (package / 'SHA256SUMS').touch()
            root = package / 'fluidd'
            source = package / 'staged'
            backup = package / '.m300-fluidd.123.previous'
            arguments = ['install-orange-pi.py', '--update-fluidd', '--port', '4480']
            with patch.object(installer, 'PACKAGE', package), \
                 patch.object(installer.os, 'geteuid', return_value=1000), \
                 patch.object(sys, 'argv', arguments), patch.object(installer, 'printer') as printer, \
                 patch.object(installer, 'require_idle') as idle, \
                 patch.object(installer, 'apply_host') as apply, \
                 patch.object(installer, 'extract_web', return_value=source), \
                 patch.object(installer, 'select_fluidd', return_value=(root, 4480, 'explicit')), \
                 patch.object(installer, 'nginx_probe_hosts', return_value=('192.168.4.157',)), \
                 patch.object(installer, 'deploy_web', return_value=backup) as deploy, \
                 patch.object(installer, 'run') as run, patch('builtins.print') as report:
                installer.main()
            for host_call in (printer, idle, apply):
                host_call.assert_not_called()
            deploy.assert_called_once_with(source, root, port=4480, hosts=('192.168.4.157',))
            self.assertEqual([call.args[:2] for call in run.call_args_list],
                             [('sha256sum', '-c'), ('sudo', '-v'), ('sudo', 'nginx')])
            self.assertEqual(json.loads(report.call_args.args[0]), {
                'status': 'INSTALLED_M300_FLUIDD', 'fluidd_root': str(root),
                'fluidd_port': 4480, 'selection': 'explicit', 'fluidd_http_verified': True,
                'fluidd_backup': str(backup), 'mcu_flashed': False})

    def check_geometry_flag(self, enabled):
        import sys
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            package=Path(folder);(package/'SHA256SUMS').write_text('')
            info=dict(state='ready',klipper_path='/home/klipper/klipper',
                      config_file='/home/klipper/printer_data/config/printer.cfg')
            arguments=['install-orange-pi.py','--port','4480']
            if enabled:arguments.append('--qualified-first-print-z')
            seen=[]
            def run(*args,**kw):
                if 'install.py' in args:
                    seen.append(args)
                    self.assertEqual('--qualified-first-print-z' in args,enabled)
                    raise ValueError('test preflight stopped before any deployment')
                return ''
            with patch.object(installer,'PACKAGE',package),patch.object(installer.os,'geteuid',return_value=1000),\
                 patch.object(installer,'require_idle',return_value=info),patch.object(installer,'run',side_effect=run),\
                 patch.object(sys,'argv',arguments),patch('sys.stderr'):
                with self.assertRaises(SystemExit):installer.main()
            self.assertEqual(len(seen),1)

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
        with patch.object(installer, 'run') as run, patch.object(installer, 'wait_ready'):
            installer.apply_host(Path('/package/host'), (), {'status': 'ALREADY_M300_HOST'})
        run.assert_not_called()

    def test_web_update_preserves_config_and_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            backup = installer.deploy_web(source, root, execute=self.local_run)
            self.assertEqual((backup / 'index.html').read_text(), 'old')
            self.assertEqual((root / 'index.html').read_text(), 'new')
            self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
            with patch.object(installer, 'run') as run:
                self.assertIsNone(installer.deploy_web(source, root, execute=run))
            run.assert_not_called()

    def test_failed_nginx_reload_restores_web_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))

            def fail_reload(sudo, *args, **kwargs):
                if args[0] == 'systemctl':
                    raise subprocess.CalledProcessError(1, args)
                return self.local_run(sudo, *args, **kwargs)

            with self.assertRaises(subprocess.CalledProcessError):
                installer.deploy_web(source, root, execute=fail_reload)
            self.assertEqual((root / 'index.html').read_text(), 'old')
            self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['new', 'web'])

    def test_web_repack_normalizes_modes_and_skips_equal_healthy_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            first, second = base / 'first.zip', base / 'second.zip'
            index, asset = self.fixture_site()
            for year, archive in ((2025, first), (2026, second)):
                with ZipFile(archive, 'w') as bundle:
                    bundle.writestr(ZipInfo('fluidd-m300/index.html', (year, 1, 1, 0, 0, 0)), index)
                    bundle.writestr('fluidd-m300/' + asset, 'new JavaScript')
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            old_umask = os.umask(0o077)
            try:
                source = installer.extract_web(first, base / 'first')
                identical = installer.extract_web(second, base / 'second')
            finally:
                os.umask(old_umask)
            for name in ('index.html', asset):
                self.assertEqual(stat.S_IMODE((source / name).stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((source / 'assets').stat().st_mode), 0o755)
            root = base / 'web'
            root.mkdir(mode=0o755)
            (root / 'index.html').write_text('old')
            installer.deploy_web(source, root, execute=self.local_run)
            (root / installer.LEGACY_WEB_MARKER).write_text('sha-of-the-previous-zip\n')
            with patch.object(installer, 'run') as run:
                self.assertIsNone(installer.deploy_web(identical, root, execute=run))
            run.assert_not_called()
            (root / asset).chmod(0o600)
            (root / 'assets').chmod(0o700)
            self.assertIsNotNone(installer.deploy_web(identical, root, execute=self.local_run))
            self.assertEqual(stat.S_IMODE((root / asset).stat().st_mode), 0o644)
            self.assertEqual(stat.S_IMODE((root / 'assets').stat().st_mode), 0o755)

    def test_zero_byte_index_and_primary_js_are_repaired_on_the_known_fluidd_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            _, main = self.fixture_site()
            others = ('assets/runtime-B0Z9INg1.js', 'assets/vendor-Cm_fBn2c.js',
                      'assets/index-3NtwrhNh.css')
            index = '<title>Fluidd</title><script type="module" src="./' + main + '"></script>'
            index += ''.join(f'<link href="./{name}">' for name in others)
            for directory in (source, root):
                (directory / 'assets').mkdir()
                for name in (main, *others):
                    (directory / name).write_text('packaged Fluidd startup asset ' + name)
                (directory / 'manifest.webmanifest').write_text('{"name":"Fluidd"}')
            (source / 'index.html').write_text(index)
            (root / 'index.html').write_bytes(b'')
            (root / main).write_bytes(b'')
            with self.serving(root) as port:
                config = f'server {{ listen {port}; root {root}; }}'
                self.assertEqual(installer.select_fluidd(config, port, repair_source=source)[0], root)
                self.assertEqual(installer.local_web_host(root, port, repair_source=source),
                                 ('127.0.0.1', False))
                for name in ('manifest.webmanifest', others[0]):
                    (root / name).write_text('foreign data')
                    with self.assertRaisesRegex(ValueError, 'dedicated Fluidd'):
                        installer.select_fluidd(config, port, repair_source=source)
                    (root / name).write_bytes((source / name).read_bytes())
                backup = installer.deploy_web(source, root, port=port, execute=self.local_run)
                self.assertEqual((backup / 'index.html').read_bytes(), b'')
                self.assertEqual((backup / main).read_bytes(), b'')
                self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
                self.assertEqual(installer.local_web_host(root, port, repair_source=source),
                                 ('127.0.0.1', True))

    def test_identical_web_files_do_not_hide_degraded_http_startup_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            index, main = self.fixture_site()
            css = 'assets/index-3NtwrhNh.css'
            for directory in (source, root):
                (directory / 'index.html').write_text(index + f'<link href="./{css}">')
                (directory / 'assets').mkdir()
                (directory / main).write_text('packaged code')
                (directory / css).write_text('packaged styles')
            reloaded = False

            class Handler(QuietHTTPHandler):
                def do_GET(self):
                    if not reloaded and self.path.startswith('/' + css):
                        self.send_error(403)
                    else:
                        super().do_GET()

            def execute(sudo, *args, **kwargs):
                nonlocal reloaded
                if args[0] == 'systemctl':
                    reloaded = True
                return self.local_run(sudo, *args, **kwargs)

            with self.serving(root, Handler) as port:
                self.assertTrue(installer.same_web_contents(source, root, http_verified=False))
                self.assertEqual(installer.local_web_host(root, port), ('127.0.0.1', False))
                self.assertIsNotNone(installer.deploy_web(source, root, port=port, execute=execute))
                self.assertEqual(installer.local_web_host(root, port), ('127.0.0.1', True))

    def test_web_http_asset_failure_restores_prior_site_after_successful_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            index, asset = self.fixture_site()
            for directory in (source, root):
                (directory / 'index.html').write_text(index)
                (directory / 'assets').mkdir()
                (directory / asset).write_text(directory.name)
            reloads = []

            class Handler(QuietHTTPHandler):
                def do_GET(self):
                    if len(reloads) == 1 and self.path.startswith('/assets/'):
                        self.send_error(403)
                    else:
                        super().do_GET()

            def execute(sudo, *args, **kwargs):
                if args[0] == 'systemctl':
                    reloads.append(args)
                return self.local_run(sudo, *args, **kwargs)

            with self.serving(root, Handler) as port, patch.object(installer, 'WEB_RELOAD_TIMEOUT', 0):
                self.assertEqual(installer.local_web_host(root, port), ('127.0.0.1', True))
                with self.assertRaisesRegex(ValueError, 'did not serve'):
                    installer.deploy_web(source, root, port=port, execute=execute)
                self.assertEqual((root / asset).read_text(), 'web')
                self.assertEqual(installer.local_web_host(root, port), ('127.0.0.1', True))
                self.assertEqual(len(reloads), 2)

    def test_http_503_cannot_report_success_for_identical_files(self):
        class Offline(QuietHTTPHandler):
            def do_GET(self):
                self.send_error(503)
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            index, js = self.fixture_site()
            for directory in (source, root):
                (directory / 'index.html').write_text(index)
                (directory / 'assets').mkdir()
                (directory / js).write_text('packaged')
            with self.serving(root, Offline) as port:
                with self.assertRaisesRegex(ValueError, 'FLUIDD_HTTP_UNVERIFIED'):
                    installer.deploy_web(source, root, port=port, execute=self.local_run)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['new', 'web'])

    def test_verify_site_bound_only_to_selected_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, root = self.web_paths(Path(tmp))
            index, js = self.fixture_site()
            (source / 'index.html').write_text(index)
            (source / 'assets').mkdir()
            (source / js).write_text('bundle')
            with self.serving(root, address='127.0.0.2') as port:
                conf = f'server {{ listen 127.0.0.2:{port}; root "{root}"; }}'
                hosts = installer.nginx_probe_hosts(conf, port, root)
                self.assertEqual(hosts, ('127.0.0.2',))
                backup = installer.deploy_web(source, root, port=port, hosts=hosts,
                                              execute=self.local_run)
                self.assertTrue(backup.is_dir())
                self.assertEqual(installer.local_web_host(root, port, hosts=hosts),
                                 ('127.0.0.2', True))

    def test_web_backup_restore_uses_verified_site_and_http_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp)
            source, root = self.web_paths(package)
            index, js = self.fixture_site()
            for directory in (root, source):
                (directory / 'index.html').write_text(index)
                (directory / 'assets').mkdir()
                (directory / js).write_text(directory.name)
            with self.serving(root) as port:
                previous = installer.deploy_web(source, root, port=port, execute=self.local_run)
                (root / 'config.json').write_text('{"custom":"edited after update"}')
                self.assertEqual(installer.rollback_web_source(previous, root), previous)
                alias = previous.with_name('.m300-fluidd.AAAAAA.previous')
                alias.symlink_to(previous)
                for bad in (Path(previous.name), source, root, alias):
                    with self.assertRaises(ValueError):
                        installer.rollback_web_source(bad, root)
                real_deploy, real_run = installer.deploy_web, installer.run
                def execute(sudo, *args, **kwargs):
                    if args[0] not in ('systemctl', 'chown'):
                        return real_run(*args, **kwargs)
                def deploy(*args, **kwargs):
                    return real_deploy(*args, execute=execute, **kwargs)
                def command(*args, **kwargs):
                    if args[:2] == ('sudo', 'nginx'):
                        return f'server {{ listen 127.0.0.1:{port}; root "{root}"; }}'
                    self.assertIn(args[:2], (('sha256sum','-c'), ('sudo','-v')))
                (package/'SHA256SUMS').touch()
                argv = ['installer', '--restore-fluidd', str(previous), '--port', str(port)]
                with patch.object(installer,'PACKAGE',package), patch.object(sys,'argv',argv), \
                     patch.object(installer.os,'geteuid',return_value=1000), \
                     patch.object(installer,'run',command), patch.object(installer,'deploy_web',deploy), \
                     patch.object(installer,'extract_web',return_value=source), patch('builtins.print') as output:
                    installer.main()
                    receipt = json.loads(output.call_args.args[0])
                    self.assertEqual(receipt['status'], 'RESTORED_M300_FLUIDD')
                    self.assertTrue(receipt['fluidd_http_verified'])
                    self.assertEqual((Path(receipt['fluidd_backup']) / js).read_text(), source.name)
                    self.assertEqual((root / js).read_text(), 'web')
                    self.assertEqual((previous / js).read_text(), 'web')
                    self.assertEqual((root / 'config.json').read_text(), '{"custom":"edited after update"}')
                    installer.main()
                    self.assertIsNone(json.loads(output.call_args.args[0])['fluidd_backup'])

    def test_interrupt_before_or_after_atomic_exchange_preserves_site(self):
        for after_exchange in (False, True):
            with self.subTest(after_exchange=after_exchange), tempfile.TemporaryDirectory() as tmp:
                source, root = self.web_paths(Path(tmp))

                def cut(sudo, *args, **kwargs):
                    exchange = installer.EXCHANGE_DIRS in args
                    if exchange and not after_exchange:
                        os._exit(71)
                    result = self.local_run(sudo, *args, **kwargs)
                    if exchange:
                        os._exit(72)
                    return result

                pid = os.fork()
                if not pid:
                    try:
                        installer.deploy_web(source, root, execute=cut)
                    finally:
                        os._exit(1)
                _, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 72 if after_exchange else 71)
                self.assertEqual((root / 'index.html').read_text(), 'new' if after_exchange else 'old')
                self.assertEqual((root / 'config.json').read_text(), '{"custom":true}')
                installer.deploy_web(source, root, execute=self.local_run)
                self.assertEqual((root / 'index.html').read_text(), 'new')

    @staticmethod
    def fixture_site():
        asset = 'assets/index-DJ1P78PQ.js'
        return f'<title>Fluidd</title><script type="module" src="./{asset}"></script>', asset

    @staticmethod
    @contextmanager
    def serving(root, handler=QuietHTTPHandler, address='127.0.0.1'):
        with ThreadingHTTPServer((address, 0), partial(handler, directory=root)) as server:
            server_thread = Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            try:
                yield server.server_address[1]
            finally:
                server.shutdown()
                server_thread.join()

    @staticmethod
    def web_paths(parent):
        source, root = parent / 'new', parent / 'web'
        source.mkdir()
        root.mkdir()
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
