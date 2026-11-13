"""Exercise startup counter synchronization and durable recovery."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import test_display  # staged payload imports
from payload.m300_counter_sync import CounterJournal, CounterRecoveryError, CounterSync
from payload.m300_nvm import HostNVM


class Fixture:
    def __init__(self, total=125., minutes=300):
        self.serial = 0x12345678
        self.snapshot = {'identity': {'machine_id': 'm300'},
                         'counters': {'print_seconds': total}}
        self.data = None
        self.minutes = minutes
        self.source = 0
        self.crc = 0x12349876
        self.state = 1
        self.events = []
        self.validate_backup = Mock()

    def query(self):
        return dict(serial=self.serial, state=self.state,
                    source=self.source if self.state == 1 else 255,
                    print_minutes=self.minutes if self.state == 1 else 0,
                    settings_crc=self.crc if self.state == 1 else 0)

    def save(self, data):
        self.events.append(('save', deepcopy(data)))
        self.data = deepcopy(data)

    def commit(self, args):
        self.events.append(('commit', args))
        pending = self.data['pending']
        assert args == [self.serial, *(pending[key] for key in
                          ('source', 'expected', 'target', 'settings_crc'))]
        if self.minutes == pending['target']:
            return dict(status=1)
        self.minutes = pending['target']
        self.source = 1 - pending['source']
        self.state = 1
        return dict(status=0)

    def run(self, sync=None, *, validate=True, commit=None):
        sync = sync or CounterSync()
        sync.run(self.snapshot, lambda: deepcopy(self.data), self.save,
                 self.query, commit or self.commit,
                 self.validate_backup if validate else None)
        return sync


class CounterSyncTests(unittest.TestCase):
    def test_disabled_without_backup_only_reads_bank_status(self):
        h = Fixture()
        h.query = Mock(wraps=h.query)
        sync = h.run(validate=False)
        self.assertEqual((sync.status, sync.banks, sync.active_bank),
                         ('DISABLED', 'NORMALIZED', 'A'))
        h.query.assert_called_once()
        self.assertEqual(h.events, [])

    def test_durable_intent_precedes_mcu_commit_and_subminute_residual_is_kept(self):
        h = Fixture()
        sync = h.run()
        self.assertEqual([event[0] for event in h.events], ['save', 'commit', 'save'])
        self.assertEqual((sync.minutes, sync.committed_seconds, sync.status),
                         (302, 120, 'SYNCED'))
        self.assertEqual((sync.banks, sync.active_bank), ('NORMALIZED', 'B'))
        h.snapshot['counters']['print_seconds'] = 185.
        again = h.run()
        self.assertEqual((again.minutes, again.committed_seconds), (303, 180))

    def test_idempotent_retry_after_ack_was_lost(self):
        h = Fixture()
        def lose_ack(args):
            h.commit(args)
            raise OSError('connection interrupted')
        with self.assertRaises(CounterRecoveryError):
            h.run(commit=lose_ack)
        self.assertIsNotNone(h.data['pending'])
        h.snapshot['counters']['print_seconds'] = 241.
        def configured_mcu(args):
            if args == [h.serial, 0, 300, 302, h.crc] and h.minutes == 302:
                return dict(status=1)
            return dict(status=2)
        again = h.run(commit=configured_mcu)
        self.assertFalse(again.flash_written)
        self.assertEqual((h.minutes, again.committed_seconds), (302, 120))
        self.assertFalse(again.display_blocked)
        self.assertEqual(h.run().committed_seconds, 240)
        self.assertEqual(h.minutes, 304)

    def test_interrupted_bank_reuses_the_same_host_intent(self):
        h = Fixture()
        def fail(args):
            h.state = 2
            return dict(status=5)
        with self.assertRaises(CounterRecoveryError):
            h.run(commit=fail)
        pending = deepcopy(h.data['pending'])
        self.assertEqual(h.run().status, 'SYNCED')
        self.assertEqual(h.events[-2][1][1:],
                         [pending[key] for key in ('source', 'expected', 'target', 'settings_crc')])

    def test_interrupted_banks_require_prior_intent_and_valid_backup(self):
        h = Fixture()
        h.state = 2
        with self.assertRaises(CounterRecoveryError):
            h.run()
        with self.assertRaises(CounterRecoveryError):
            h.run(validate=False)
        self.assertEqual(h.events, [])
        h.state = 1
        with self.assertRaises(CounterRecoveryError):
            h.run(commit=lambda args: dict(status=5))
        h.state = 2
        h.validate_backup.side_effect = OSError('backup missing')
        with self.assertRaises(CounterRecoveryError):
            h.run()
        with self.assertRaises(CounterRecoveryError):
            h.run(validate=False)
        self.assertIsNotNone(h.data['pending'])

    def test_corrupt_journal_on_interrupted_banks_stops_startup(self):
        h = Fixture()
        h.state = 2
        with self.assertRaisesRegex(CounterRecoveryError, 'bad journal'):
            CounterSync().run(h.snapshot, Mock(side_effect=ValueError('bad journal')),
                              h.save, h.query, h.commit)
        self.assertEqual(h.events, [])

    def test_missing_factory_counter_without_opt_in_keeps_host_startup_available(self):
        h = Fixture()
        h.state = 0
        sync = h.run(validate=False)
        self.assertEqual((sync.status, sync.banks), ('DISABLED', 'UNAVAILABLE'))
        self.assertEqual(h.events, [])

    def test_pending_never_applies_to_changed_state_or_another_printer(self):
        h = Fixture()
        with self.assertRaises(CounterRecoveryError):
            h.run(commit=lambda args: dict(status=5))
        h.crc ^= 1
        with self.assertRaisesRegex(ValueError, 'changed during'):
            h.run()
        h.serial += 1
        with self.assertRaisesRegex(ValueError, 'another printer'):
            h.run()
        self.assertEqual(len(h.events), 1)

    def test_external_stock_work_is_preserved_and_rollback_refused(self):
        h = Fixture(total=15.)
        self.assertEqual(h.run().status, 'CURRENT')
        h.minutes += 15
        self.assertEqual(h.run().status, 'CURRENT')
        h.minutes -= 1
        with self.assertRaisesRegex(ValueError, 'went backwards'):
            h.run()
        h.minutes += 1
        h.snapshot['counters']['print_seconds'] = 72.
        self.assertEqual(h.run().committed_seconds, 60)
        self.assertEqual(h.minutes, 316)

    def test_configured_mcu_defers_and_backup_removal_retains_ui_accounting(self):
        h = Fixture()
        sync = h.run(commit=lambda args: dict(status=2))
        self.assertEqual(sync.status, 'AWAITING_FIRMWARE_RESTART')
        self.assertTrue(sync.pending)
        self.assertEqual(h.run().status, 'SYNCED')
        h.snapshot['counters']['print_seconds'] += 180.
        again = h.run(validate=False)
        self.assertEqual((again.status, again.committed_seconds, h.minutes),
                         ('BACKUP_REQUIRED', 120, 302))

    def test_missing_backup_after_mcu_applied_pending_hides_unreconciled_total(self):
        h = Fixture()
        def lose_ack(args):
            h.commit(args)
            raise OSError('lost acknowledgement')
        with self.assertRaises(CounterRecoveryError):
            h.run(commit=lose_ack)
        commit = Mock()
        sync = h.run(validate=False, commit=commit)
        self.assertTrue(sync.display_blocked)
        self.assertEqual(sync.status, 'BACKUP_REQUIRED')
        commit.assert_not_called()

    def test_verification_mismatch_keeps_durable_pending_state(self):
        h = Fixture()
        def unverified(args):
            h.commit(args)
            h.crc ^= 1
            return dict(status=0)
        with self.assertRaisesRegex(CounterRecoveryError, 'read-back'):
            h.run(commit=unverified)
        self.assertEqual(h.data['committed'], 0)
        self.assertEqual(h.data['pending']['target'], 302)

    def test_rejected_backup_and_failed_journal_write_send_no_commit(self):
        h = Fixture()
        commit = Mock()
        h.validate_backup.side_effect = ValueError('backup serial mismatch')
        with self.assertRaisesRegex(ValueError, 'backup serial'):
            h.run(commit=commit)
        h.validate_backup.side_effect = None
        h.save = Mock(side_effect=OSError('fsync failed'))
        with self.assertRaisesRegex(OSError, 'fsync failed'):
            h.run(commit=commit)
        commit.assert_not_called()

    def test_journal_load_checks_integrity_and_does_not_reset_corruption(self):
        with TemporaryDirectory() as directory:
            store = HostNVM(str(Path(directory) / 'settings.json'), 'm300', 'mechanics')
            journal = CounterJournal(store)
            self.assertIsNone(journal.load())
            h = Fixture()
            h.run()
            journal.save(h.data)
            self.assertEqual(journal.load(), h.data)
            path = Path(journal.path)
            path.write_text(path.read_text().replace('302', '303'))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                journal.load()


if __name__ == '__main__':
    unittest.main()
