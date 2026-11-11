from copy import deepcopy
import json
from pathlib import Path
import unittest
import acceptance_register as m

class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((m.ROOT/'docs/reports/HARDWARE_ACCEPTANCE.json').read_text())
    def test_valid_and_markdown_exact(self):
        self.assertEqual(m.validate(self.data),21)
        self.assertEqual(m.render(self.data),(m.ROOT/'docs/pl/ACCEPTANCE_REGISTER.md').read_text())
    def test_confirmed_needs_user_evidence(self):
        d=deepcopy(self.data);d['features'][0]['events'][0]['evidence']={'kind':'ci_pass','quote':'741 tests'}
        with self.assertRaises(AssertionError):m.validate(d)
    def test_unknown_cannot_become_pass_without_evidence(self):
        d=deepcopy(self.data);pending=next(f for f in d['features'] if f['id']=='FIRST_LAYER')
        pending['events'][-1]['status']='CONFIRMED_HARDWARE'
        with self.assertRaises(AssertionError):m.validate(d)
    def test_duplicate_id_rejected(self):
        d=deepcopy(self.data);d['features'].append(deepcopy(d['features'][0]))
        with self.assertRaises(AssertionError):m.validate(d)
    def test_rejection_not_erased_by_pending_new_release(self):
        f=next(f for f in self.data['features'] if f['id']=='OLED_SHARP')
        self.assertEqual([e['status'] for e in f['events']],['REJECTED_VISUAL','AWAITING_TEST'])
    def test_known_layout_acceptance_kept_narrow(self):
        f=next(f for f in self.data['features'] if f['id']=='OLED_LAYOUT')
        self.assertEqual(f['events'][-1]['status'],'CONFIRMED_UI')
        self.assertNotEqual(f['events'][-1]['status'],'CONFIRMED_HARDWARE')
    def test_no_unperformed_hardware_pass(self):
        for f in self.data['features']:
            for e in f['events']:self.assertNotEqual(e['status'],'CONFIRMED_HARDWARE')
    def test_mandatory_fields_validated(self):
        for key in ('date','version','test','result'):
            d=deepcopy(self.data);d['features'][0]['events'][0][key]=''
            with self.assertRaises(AssertionError):m.validate(d)

if __name__=='__main__':unittest.main(verbosity=2)
