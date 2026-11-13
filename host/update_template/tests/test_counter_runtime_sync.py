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
from payload.m300_counter_sync import (CounterJournal, RUNTIME_COMMIT_FORMAT,
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
    def setup_controller(self):
        hw, _, _ = hardware_fixture()
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
        hw.counter_backup = '/verified-backup.bin'
        hw._counter_validator = lambda nvm: fixture.validate_backup
        journal = CounterJournal(store)

        def commit(args):
            self.assertTrue(mutex.test())
            fixture.data = journal.load()
            return fixture.commit(args)

        transport = NS(query=Mock(side_effect=fixture.query), commit=Mock(side_effect=commit))
        return NS(hw=hw, nvm=nvm, reactor=reactor, fixture=fixture, journal=journal,
                  transport=transport, commit=commit, heat=heat, pwm=pwm, mutex=mutex,
                  objects=objects, print_state=print_state)

    def test_ready_and_post_job_checkpoint_queue_sync_without_restart(self):
        h = self.setup_controller()
        h.hw.counter_runtime_supported = True
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
        self.assertIsNone(h.journal.load())
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
        h.fixture.validate_backup.side_effect = lambda serial: h.print_state.update(state='printing')
        self.assertLess(h.hw._runtime_counter_tick(10.), h.reactor.NEVER)
        h.transport.commit.assert_not_called()
        self.assertIsNotNone(h.journal.load()['pending'])
        self.assertEqual(h.hw.counter_sync.status, 'AWAITING_IDLE')
        h.fixture.validate_backup.side_effect = None
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
                if directory_calls == 2:
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
