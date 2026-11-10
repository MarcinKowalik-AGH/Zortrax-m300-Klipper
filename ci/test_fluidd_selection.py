"""No network, sudo, service changes or printer commands in these tests."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install_orange_pi as m


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.web('fluidd-a'); self.b = self.web('fluidd-b')

    def web(self, name, title='fluidd'):
        p = self.root / name; p.mkdir()
        (p/'index.html').write_text('<html><title>'+title+'</title></html>')
        return p

    def config(self, pairs):
        return '\n'.join('server { listen '+str(port)+'; root "'+str(root)+'"; }'
                         for port,root in pairs)

    def test_default_port_is_4480(self):
        self.assertEqual(m.DEFAULT_FLUIDD_PORT,4480)
        self.assertEqual(m.select_fluidd(self.config([(4480,self.a)])),
                         (self.a,4480,'default-4480'))

    def test_default_4480_preferred_to_other_valid_site(self):
        self.assertEqual(m.select_fluidd(self.config([(80,self.b),(4480,self.a)]))[0],self.a)

    def test_legacy_unique_4080_is_not_moved(self):
        self.assertEqual(m.select_fluidd(self.config([(4080,self.a)])),
                         (self.a,4080,'unique-nginx-detection'))

    def test_fresh_kiauh_unique_80_is_not_rewritten(self):
        self.assertEqual(m.select_fluidd(self.config([(80,self.a)]))[1],80)

    def test_explicit_port_wins(self):
        self.assertEqual(m.select_fluidd(self.config([(4480,self.a),(8080,self.b)]),8080)[0],self.b)

    def test_explicit_missing_port_does_not_fallback(self):
        with self.assertRaises(ValueError): m.select_fluidd(self.config([(4480,self.a)]),4080)

    def test_ipv4_ipv6_one_site(self):
        cfg=f'http {{ server {{ listen 127.0.0.1:4480; listen [::]:4480; root "{self.a}"; }} }}'
        self.assertEqual(m.select_fluidd(cfg)[0],self.a)

    def test_root_location_and_proxied_paths(self):
        cfg=f'server {{ listen 4480; location / {{ root "{self.a}"; }} location /websocket {{ proxy_pass http://moonraker; }} }}'
        self.assertEqual(m.select_fluidd(cfg)[0],self.a)

    def test_ambiguous_preferred_port_fails(self):
        with self.assertRaises(ValueError):
            m.select_fluidd(self.config([(4480,self.a),(4480,self.b),(80,self.b)]))

    def test_two_other_fluidd_instances_fail(self):
        with self.assertRaisesRegex(ValueError,'exactly one'):
            m.select_fluidd(self.config([(80,self.a),(4080,self.b)]))

    def test_one_root_on_two_ports_needs_explicit_choice(self):
        with self.assertRaises(ValueError):m.select_fluidd(self.config([(80,self.a),(8080,self.a)]))

    def test_nonfluidd_site_is_excluded(self):
        other=self.web('other','Mainsail')
        self.assertEqual(m.select_fluidd(self.config([(80,other),(8080,self.a)]))[0],self.a)

    def test_git_root_refused(self):
        (self.a/'.git').mkdir()
        with self.assertRaises(ValueError):m.select_fluidd(self.config([(4480,self.a)]))

    def test_variable_root_refused(self):
        with self.assertRaises(ValueError):m.select_fluidd('server { listen 4480; root $web_root; }')

    def test_explicit_root_resolves_actual_port(self):
        self.assertEqual(m.select_fluidd(self.config([(8080,self.a)]),root=self.a),
                         (self.a,8080,'explicit-root'))

    def test_explicit_root_requires_port_when_unresolvable(self):
        with self.assertRaises(ValueError):m.select_fluidd('',root=self.a)

    def test_explicit_root_port_can_override_parser(self):
        self.assertEqual(m.select_fluidd('',port=4480,root=self.a),(self.a,4480,'explicit'))

    def test_saved_state_revalidated_not_just_trusted(self):
        m.save_install_state(self.root,self.b,8080)
        state=m.load_install_state(self.root)
        self.assertEqual(m.select_fluidd(self.config([(4480,self.a),(8080,self.b)]),saved=state),
                         (self.b,8080,'saved-revalidated'))

    def test_saved_port_changed_requires_explicit_override(self):
        m.save_install_state(self.root,self.a,4080)
        state=m.load_install_state(self.root)
        with self.assertRaisesRegex(ValueError,'no longer matches'):
            m.select_fluidd(self.config([(4480,self.a)]),saved=state)
        self.assertEqual(m.select_fluidd(self.config([(4480,self.a)]),4480,saved=state)[1],4480)

    def test_saved_root_changed_is_not_silently_updated(self):
        m.save_install_state(self.root,self.a,4480)
        with self.assertRaises(ValueError):
            m.select_fluidd(self.config([(4480,self.b)]),saved=m.load_install_state(self.root))

    def test_atomic_receipt_outside_package_no_extra_files(self):
        before=set(self.root.iterdir())
        path=m.save_install_state(self.root,self.a,4480)
        self.assertEqual(set(self.root.iterdir())-before,{path})
        self.assertEqual(path.name,'.m300-installer.json')
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(json.loads(path.read_text())['fluidd_port'],4480)

    def test_failed_receipt_write_preserves_old_state(self):
        path=m.save_install_state(self.root,self.a,4480); old=path.read_bytes()
        with patch.object(m.os,'replace',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):m.save_install_state(self.root,self.b,8080)
        self.assertEqual(path.read_bytes(),old)
        self.assertFalse(list(self.root.glob('.m300-installer-*')))

    def test_missing_receipt_is_normal(self):
        self.assertIsNone(m.load_install_state(self.root))

    def test_corrupt_receipts_refused(self):
        p=self.root/m.INSTALL_STATE_NAME
        for s in ('{','[]','{}',json.dumps(dict(schema=2,fluidd_root=str(self.a),fluidd_port=4480)),
                  json.dumps(dict(schema=1,fluidd_root='relative',fluidd_port=4480))):
            with self.subTest(value=s):
                p.write_text(s)
                with self.assertRaises(ValueError):m.load_install_state(self.root)

    def test_invalid_ports(self):
        for v in (True,False,0,-1,65536,None,'word',4.5,'004480'):
            with self.subTest(value=v),self.assertRaises(ValueError):m.valid_port(v)
        for v in (1,4480,'4480',65535):self.assertEqual(m.valid_port(v),int(v))

    def test_receipt_saved_only_after_deployment(self):
        # Verify the actual entry point orders writes after deployment and readiness.
        import inspect
        source=inspect.getsource(m.main)
        self.assertLess(source.index('backup = deploy_web('),source.index('receipt = save_install_state('))
        self.assertLess(source.index('require_idle('),source.index('root, fluidd_port'))
        self.assertIn("args.port is None and args.fluidd_root is None",source)


if __name__=='__main__':unittest.main(verbosity=2)
