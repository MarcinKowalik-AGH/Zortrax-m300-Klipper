# Marcin Kowalik <mkowalik@agh.edu.pl>
"""Post-job MCU synchronization, runtime UART correlation and durable retries."""
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from test_counter_sync import Fixture
from test_hardware import fixture as hardware_fixture
from test_native_oem_services import Mutex
from payload.m300_counter_sync import (COMMIT_FORMAT, CounterJournal, CounterSync, RUNTIME_COMMIT_FORMAT,
                                      RUNTIME_QUERY_FORMAT, RUNTIME_RESULT_FORMAT,
                                      RUNTIME_STATE_FORMAT)
from payload.m300_hardware import (COUNTER_TIMEOUT, COUNTER_WINDOW,
                                   RuntimeCounterTransport)
from payload.m300_nvm import HostNVM


class Wire:
    def __init__(self, now):
        self.now = now
        self.responses = {}
        self.sends = []
        self.dispatch = lambda name, args: None
        self.wait_deadlines = []
        self.reactor = NS(monotonic=lambda: self.now, completion=self.completion,
                          async_complete=lambda done, data: setattr(done, 'data', data))
        self.mcu = NS(lookup_command=lambda name: NS(send=lambda args: self.send(name, args)),
                      register_serial_response=lambda cb, name: self.responses.__setitem__(name, cb),
                      estimated_print_time=lambda now: now,
                      print_time_to_clock=lambda ptime: int(ptime * 72_000_000))

    def completion(self):
        done = NS(data=None)
        def wait(deadline):
            self.wait_deadlines.append(deadline)
            return done.data
        done.wait = wait
        return done

    def send(self, name, args):
        self.sends.append((name, args))
        self.dispatch(name, args)

    def reply(self, fmt, **fields):
        self.responses[fmt]({'#sent_time': 0., '#receive_time': self.now + .05, **fields})


class RuntimeTransportTests(unittest.TestCase):
    def test_commit_correlates_deadline_even_after_serial_retransmission(self):
        wire = Wire(61.)  # A 72 MHz uint32 timer has already wrapped.
        transport = RuntimeCounterTransport(wire.mcu, wire.reactor)
        args = [0x12345678, 0, 300, 302, 123]

        def dispatch(name, sent):
            self.assertEqual(name, RUNTIME_COMMIT_FORMAT)
            deadline = wire.mcu.print_time_to_clock(wire.now + COUNTER_WINDOW) & 0xffffffff
            self.assertEqual(sent, args + [deadline])
            wire.reply(RUNTIME_RESULT_FORMAT, deadline=deadline - 1, status=0)
            wire.reply(RUNTIME_RESULT_FORMAT, deadline=deadline, status=2)

        wire.dispatch = dispatch
        self.assertEqual(transport.commit(args)['status'], 2)
        self.assertEqual(wire.wait_deadlines, [wire.now + COUNTER_TIMEOUT])
        self.assertIsNone(transport.pending)

    def test_query_ignores_old_readback_and_missing_result_times_out(self):
        wire = Wire(1.)
        transport = RuntimeCounterTransport(wire.mcu, wire.reactor)

        def dispatch(name, sent):
            self.assertEqual(name, RUNTIME_QUERY_FORMAT)
            wire.reply(RUNTIME_STATE_FORMAT, token=sent[0] ^ 1, print_minutes=1)
            wire.reply(RUNTIME_STATE_FORMAT, token=sent[0], print_minutes=302)

        wire.dispatch = dispatch
        self.assertEqual(transport.query()['print_minutes'], 302)
        wire.dispatch = lambda name, sent: wire.reply(
            RUNTIME_STATE_FORMAT, token=sent[0] ^ 1, print_minutes=1)
        with self.assertRaisesRegex(TimeoutError, 'state response timed out'):
            transport.query()
        self.assertIsNone(transport.pending)


class RuntimeSynchronizationTests(unittest.TestCase):
    def setup_controller(self, *, legacy_backup=None, enrolled=True):
        hw, _, _ = hardware_fixture(legacy_backup=legacy_backup)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = HostNVM(str(Path(temp.name) / 'settings.json'), 'm300', 'mechanics')
        store.update(lambda data: data['counters'].update(print_seconds=125.))
        nvm = NS(store=store, executor=NS(submit=lambda fn, *args: fn(*args)),
                 ui_snapshot=store.snapshot, runtime_is_checkpointed=Mock(return_value=True),
                 get_status=lambda now: {'state': 'IDLE', 'busy': False})
        fixture = Fixture()
        mutex = Mutex()
        pwm = NS(get_mcu=lambda: hw.mcu, _last_clock=0)
        heat = {'target': 0., 'power': 0.}
        heater = NS(mcu_pwm=pwm, get_status=lambda now: heat)
        print_state = {'state': 'complete'}
        objects = {'m300_nvm': nvm, 'virtual_sdcard': NS(is_active=lambda: False),
                   'print_stats': NS(get_status=lambda now: print_state),
                   'toolhead': NS(check_busy=lambda now: (0., now, True)),
                   'heaters': NS(lookup_heater=lambda name: heater)}
        hw.board.ready = True
        hw.board.gcode.get_mutex = lambda: mutex
        hw.printer.lookup_object = objects.get
        hw.printer.is_shutdown = Mock(return_value=False)
        hw.mcu.estimated_print_time = lambda now: now
        hw.mcu.print_time_to_clock = lambda ptime: int(ptime * 72_000_000)
        reactor = NS(monotonic=lambda: 10., NOW=0., NEVER=1.e30, register_timer=lambda fn: fn,
                     update_timer=Mock(), unregister_timer=Mock())
        hw.printer.get_reactor = lambda: reactor
        journal = CounterJournal(store)
        if enrolled:
            journal.save(fixture.data)

        def commit(args):
            self.assertTrue(mutex.test())
            fixture.data = journal.load()
            return fixture.commit(args)

        transport = NS(query=Mock(side_effect=fixture.query), commit=Mock(side_effect=commit))
        return NS(hw=hw, nvm=nvm, reactor=reactor, fixture=fixture, journal=journal,
                  transport=transport, commit=commit, heat=heat, pwm=pwm, mutex=mutex,
                  objects=objects, print_state=print_state)

    def reconcile(self, h, minutes, committed, serial='Z12345678'):
        values = dict(SERIAL=serial, MCU_MINUTES=minutes, COMMITTED_MINUTES=committed)
        gcmd = NS(get=values.__getitem__, get_int=lambda name, **kw: values[name],
                  respond_info=Mock(), error=ValueError)
        h.hw.cmd_counter_reconcile(gcmd)

    def startup(self, h, *, runtime):
        def commit(args):
            h.fixture.data = h.journal.load()
            return h.fixture.commit(args)

        send = Mock(side_effect=commit)
        h.hw.mcu.lookup_query_command = Mock(side_effect=lambda command, fmt: NS(
            send=send if command == COMMIT_FORMAT else h.fixture.query))
        h.hw.board.startup_transport = NS(_bounded=lambda name, fn: fn())
        h.hw._sync_factory_counter(dict(h.hw.mcu.get_constants(), M300_FACTORY_COUNTER_ABI=1,
                                        M300_FACTORY_COUNTER_RUNTIME_ABI=int(runtime)))
        return send

    def test_clean_host_establishes_baseline_before_first_print(self):
        h = self.setup_controller(enrolled=False)
        h.nvm.store.update(lambda d: d['counters'].update(print_seconds=0.))
        self.startup(h, runtime=True).assert_not_called()
        self.assertEqual(h.hw.counter_sync.status, 'CURRENT')
        self.assertEqual(h.journal.load()['committed'], 0)
        h.nvm.store.update(lambda d: d['counters'].update(print_seconds=125.))
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.fixture.minutes, 302)

    def test_missing_both_receipts_requires_verified_credit_before_writing(self):
        h = self.setup_controller(enrolled=False)
        self.startup(h, runtime=True).assert_not_called()
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'RECONCILIATION_REQUIRED')
        self.assertEqual(h.hw.get_status()['factory_counter_observed_minutes'], 300)
        self.assertIsNone(h.hw.get_status()['factory_print_minutes'])
        for serial, minutes, credited in [('Z12345679',300,0), ('Z12345678',301,0),
                                           ('Z12345678',300,3)]:
            with self.assertRaises(ValueError):
                self.reconcile(h, minutes, credited, serial)
        self.assertIsNone(h.journal.load())
        h.transport.commit.assert_not_called()
        self.reconcile(h, 300, 2)
        self.assertEqual(h.hw.counter_sync.status, 'CURRENT')
        self.assertEqual(h.journal.load()['committed'], 2)
        h.hw._runtime_counter_tick(10.)
        h.transport.commit.assert_not_called()

    def test_restoring_both_older_receipts_cannot_count_same_print_twice(self):
        h = self.setup_controller()
        old = Path(h.journal.path).read_bytes()
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        for path in (h.journal.path, h.journal.checkpoint):
            Path(path).write_bytes(old)
        h.hw.counter_sync = CounterSync()
        self.startup(h, runtime=True).assert_not_called()
        self.assertEqual(h.hw.counter_sync.status, 'RECONCILIATION_REQUIRED')
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.fixture.minutes, 302)
        h.transport.commit.assert_called_once()
        self.reconcile(h, 302, 2)
        self.assertEqual(h.hw.counter_sync.status, 'CURRENT')

    def test_unmirrored_stale_rc16_receipt_and_factory_advance_requires_reconciliation(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        Path(h.journal.checkpoint).unlink()
        h.fixture.minutes += 2
        h.nvm.store.update(lambda d: d['counters'].update(print_seconds=245.))
        self.startup(h, runtime=True).assert_not_called()
        self.assertEqual(h.hw.counter_sync.status, 'RECONCILIATION_REQUIRED')
        self.assertEqual(h.journal.load()['committed'], 2)
        with self.assertRaises(ValueError):
            self.reconcile(h, 304, 1)
        self.reconcile(h, 304, 4)
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.fixture.minutes, 304)
        h.transport.commit.assert_called_once()

    def test_ready_and_post_job_checkpoint_queue_sync_without_restart(self):
        h = self.setup_controller()
        self.startup(h, runtime=True).assert_not_called()
        self.assertEqual(h.journal.load()['committed'], 0)
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'AWAITING_IDLE')
        with patch('payload.m300_hardware.RuntimeCounterTransport', return_value=h.transport):
            h.hw._request_factory_info()
        h.reactor.update_timer.assert_called_once_with(h.hw.counter_timer, h.reactor.NOW)
        self.assertEqual(h.hw.counter_timer(10.), h.reactor.NEVER)
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 302)
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'SYNCED')
        self.assertEqual(h.journal.load()['committed'], 2)
        h.nvm.store.update(lambda data: data['counters'].update(print_seconds=185.))
        h.hw._queue_counter()
        self.assertEqual(h.hw.counter_timer(10.), h.reactor.NEVER)
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 303)
        self.assertEqual(h.journal.load()['committed'], 3)

    def test_old_config_path_is_ignored_when_synchronizing_existing_backlog(self):
        h = self.setup_controller(legacy_backup='removed/old-flash-dump.bin', enrolled=False)
        h.fixture.minutes = 286732
        h.nvm.store.update(lambda data: data['counters'].update(print_seconds=135660.5))
        self.startup(h, runtime=True).assert_not_called()
        with patch('payload.m300_hardware.RuntimeCounterTransport', return_value=h.transport):
            h.hw._request_factory_info()
        self.assertEqual(h.hw.counter_timer(10.), h.reactor.NEVER)
        self.assertEqual(h.hw.counter_sync.status, 'RECONCILIATION_REQUIRED')
        h.transport.commit.assert_not_called()
        self.reconcile(h, 286732, 0)
        self.assertEqual(h.hw.counter_timer(10.), h.reactor.NEVER)
        h.transport.commit.assert_called_once_with([h.fixture.serial, 0, 286732, 288993,
                                                    h.fixture.crc])
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 288993)
        self.assertEqual(h.journal.load()['committed'], 2261)

    def test_missing_journal_after_settlement_does_not_charge_again(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.fixture.minutes, 302)
        Path(h.journal.path).unlink()
        h.hw.counter_sync = CounterSync()
        self.startup(h, runtime=True).assert_not_called()
        self.assertTrue(Path(h.journal.path).is_file())
        self.assertEqual(h.hw.counter_sync.committed_seconds, 120)
        h.hw._runtime_counter_tick(10.)
        h.transport.commit.assert_called_once()
        self.assertEqual((h.fixture.minutes, h.fixture.source), (302, 1))

    def test_stale_primary_or_checkpoint_excludes_already_paid_minutes(self):
        for stale in ('path', 'checkpoint'):
            with self.subTest(stale=stale):
                h = self.setup_controller()
                h.hw.counter_runtime = h.transport
                h.hw._runtime_counter_tick(10.)
                copy = Path(getattr(h.journal, stale))
                old_receipt = copy.read_bytes()
                h.nvm.store.update(lambda data: data['counters'].update(print_seconds=245.))
                h.hw._runtime_counter_tick(10.)
                self.assertEqual((h.fixture.minutes, h.fixture.source), (304, 0))
                copy.write_bytes(old_receipt)
                h.hw.counter_sync = CounterSync()
                self.startup(h, runtime=True).assert_not_called()
                self.assertEqual(h.hw.counter_sync.committed_seconds, 240)
                h.hw._runtime_counter_tick(10.)
                self.assertEqual(h.transport.commit.call_count, 2)
                self.assertEqual(h.fixture.minutes, 304)
                # OEM increments and subsequent new host work are additive.
                h.fixture.minutes += 9
                self.startup(h, runtime=True).assert_not_called()
                h.nvm.store.update(lambda data: data['counters'].update(print_seconds=305.))
                h.hw._runtime_counter_tick(10.)
                self.assertEqual((h.fixture.minutes, h.fixture.source), (314, 1))

    def test_pending_checkpoint_recovers_after_lost_reply_and_journal_loss(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport

        def lose_reply(args):
            h.commit(args)
            raise TimeoutError('lost acknowledgement')

        h.transport.commit.side_effect = lose_reply
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.fixture.minutes, 302)
        Path(h.journal.path).unlink()
        h.hw.counter_sync = CounterSync()
        self.startup(h, runtime=True).assert_called_once()
        self.assertEqual((h.fixture.minutes, h.fixture.source), (302, 1))
        self.assertEqual(h.hw.counter_sync.committed_seconds, 120)

    def test_single_legacy_receipt_is_mirrored_even_without_backlog(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        h.hw._runtime_counter_tick(10.)
        Path(h.journal.checkpoint).unlink()
        self.startup(h, runtime=True).assert_not_called()
        self.assertEqual(Path(h.journal.path).read_bytes(), Path(h.journal.checkpoint).read_bytes())
        self.assertEqual(h.hw.counter_sync.committed_seconds, 120)

    def test_startup_only_firmware_keeps_new_backlog_on_host(self):
        h = self.setup_controller()
        self.startup(h, runtime=False).assert_not_called()
        h.hw._request_factory_info()
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 300)
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'MCU_ABI_UNAVAILABLE')
        self.assertIsNone(h.hw.counter_timer)
        self.assertEqual(h.journal.load()['committed'], 0)

    def test_startup_only_firmware_can_complete_preexisting_intent(self):
        h = self.setup_controller()
        h.journal.save(dict(serial='Z12345678', machine_id='m300', committed=0,
                            last_minutes=300, pending=dict(source=0, expected=300, target=302,
                                                           settings_crc=h.fixture.crc)))
        h.fixture.state = 2
        self.startup(h, runtime=False).assert_called_once()
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 302)
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'SYNCED')
        self.assertIsNone(h.journal.load()['pending'])

    def test_runtime_startup_rejects_another_printers_journal(self):
        h = self.setup_controller(enrolled=False)
        h.journal.save(dict(serial='Z87654321', machine_id='m300', committed=2,
                            last_minutes=302, pending=None))
        self.startup(h, runtime=True).assert_not_called()
        self.assertIsNone(h.hw.get_status()['factory_print_minutes'])
        self.assertEqual(h.hw.get_status()['factory_counter_sync'], 'REFUSED')
        h.hw.counter_runtime = h.transport
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_not_called()
        self.assertIsNone(h.hw.get_status()['factory_print_minutes'])

    def test_active_job_heat_queue_or_service_prevents_runtime_uart_access(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        for field, target, busy, last_clock, checkpointed in (
                ('printing', 0., False, 0, True), ('paused', 0., False, 0, True),
                ('complete', 60., False, 0, True), ('complete', 0., True, 0, True),
                ('complete', 0., False, 900_000_000, True),
                ('complete', 0., False, 0, False)):
            h.print_state['state'] = field
            h.heat['target'] = target
            h.pwm._last_clock = last_clock
            h.nvm.runtime_is_checkpointed.return_value = checkpointed
            h.objects['m300_maintenance'] = NS(get_status=lambda now: {
                'state': 'IDLE', 'busy': busy})
            self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
            self.assertEqual(h.hw.counter_sync.status, 'AWAITING_IDLE')
        h.transport.query.assert_not_called()
        h.transport.commit.assert_not_called()
        self.assertEqual(h.journal.load()['committed'], 0)
        h.nvm.runtime_is_checkpointed.return_value = True
        h.objects['pause_resume'] = NS(is_paused=True)
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.objects['pause_resume'].is_paused = False
        h.objects['m300_print_control'] = NS(context={})
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.query.assert_not_called()

    def test_admission_is_rechecked_after_intent_before_uart_commit(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport

        save = CounterJournal.save

        def start_print_after_save(journal, data):
            save(journal, data)
            h.print_state.update(state='printing')

        with patch.object(CounterJournal, 'save', start_print_after_save):
            self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_not_called()
        self.assertIsNotNone(h.journal.load()['pending'])
        self.assertEqual(h.hw.counter_sync.status, 'AWAITING_IDLE')
        h.print_state['state'] = 'complete'
        self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        self.assertEqual(h.hw.counter_sync.status, 'SYNCED')

    def test_motion_and_heat_defer_without_reading_service_telemetry(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        status = Mock(return_value={'state': 'IDLE', 'busy': False})
        h.objects['m300_pad_mesh'] = NS(get_status=status)
        h.objects['toolhead'].check_busy = lambda now: (now + 1., now, False)
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.objects['toolhead'].check_busy = lambda now: (now, now, True)
        h.heat['target'] = 60.
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        status.assert_not_called()
        h.transport.query.assert_not_called()

    def test_wait_reason_distinguishes_host_and_mcu_then_clears(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        h.heat['target'] = 60.
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.hw.get_status()['factory_counter_wait_reason'], 'extruder')
        h.transport.commit.assert_not_called()
        h.heat['target'] = 0.
        h.transport.commit.side_effect = lambda args: {'status': 2}
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.hw.get_status()['factory_counter_wait_reason'], 'mcu_write_window')
        self.assertTrue(h.hw.counter_sync.pending)
        h.transport.commit.side_effect = h.commit
        h.hw._runtime_counter_tick(10.)
        self.assertIsNone(h.hw.get_status()['factory_counter_wait_reason'])
        self.assertEqual(h.hw.counter_sync.status, 'SYNCED')

    def test_unsupported_target_keeps_readback_and_receipt_without_retry(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        h.transport.commit.side_effect = lambda args: {'status': 7}
        h.hw._runtime_counter_tick(10.)
        self.assertEqual(h.hw.counter_sync.status, 'UNSUPPORTED_MCU_TARGET')
        self.assertTrue(h.hw.counter_sync.pending)
        self.assertEqual(h.hw.counter_sync.committed_seconds, 0)
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 300)
        self.assertEqual(h.hw.counter_sync.banks, 'NORMALIZED')
        self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_called_once()

    def test_status_two_after_partial_write_keeps_wal_until_runtime_recovery(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport

        def interrupted(args):
            h.fixture.state = 2
            return {'status': 2}

        h.transport.commit.side_effect = interrupted
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        self.assertIsNotNone(h.journal.load()['pending'])
        self.assertIsNone(h.hw.get_status()['factory_print_minutes'])
        self.assertEqual(h.hw.get_status()['factory_counter_banks'], 'RECOVERY_REQUIRED')
        h.transport.commit.side_effect = h.commit
        self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 302)

    def test_lost_runtime_response_replays_same_commit_then_settles_once(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport

        def lose_reply(args):
            h.commit(args)
            raise TimeoutError('simulated UART response loss')

        h.transport.commit.side_effect = lose_reply
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        self.assertFalse(h.mutex.test())
        self.assertIsNotNone(h.journal.load()['pending'])
        self.assertIsNone(h.hw.get_status()['factory_print_minutes'])
        h.transport.commit.side_effect = h.commit
        self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        self.assertEqual(h.transport.commit.call_args_list[0], h.transport.commit.call_args_list[1])
        self.assertEqual((h.hw.counter_sync.minutes, h.hw.counter_sync.committed_seconds), (302, 120))
        self.assertIsNone(h.journal.load()['pending'])

    def test_visible_pending_intent_is_synced_before_any_flash_commit(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        fsync = os.fsync
        allow_directory_sync = False

        def failing_fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode) and not allow_directory_sync:
                raise OSError('intent directory sync failed after rename')
            fsync(fd)

        with patch('payload.m300_nvm.os.fsync', side_effect=failing_fsync):
            self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
            self.assertIsNotNone(h.journal.load()['pending'])
            self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
            h.transport.commit.assert_not_called()
            allow_directory_sync = True
            self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_called_once()
        self.assertEqual(h.journal.load()['committed'], 2)

    def test_visible_settled_intent_recovers_display_without_another_flash_write(self):
        h = self.setup_controller()
        h.hw.counter_runtime = h.transport
        fsync = os.fsync
        directory_calls = 0

        def failing_fsync(fd):
            nonlocal directory_calls
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                directory_calls += 1
                # Two durable intent copies precede the first settlement copy.
                if directory_calls == 3:
                    raise OSError('settlement directory sync failed after rename')
            fsync(fd)

        with patch('payload.m300_nvm.os.fsync', side_effect=failing_fsync):
            self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
            self.assertIsNone(h.journal.load()['pending'])
            self.assertIsNone(h.hw.get_status()['factory_print_minutes'])
            self.assertEqual(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_called_once()
        self.assertEqual(h.hw.get_status()['factory_print_minutes'], 302)
        self.assertEqual(h.hw.get_status()['factory_counter_committed_seconds'], 120)
