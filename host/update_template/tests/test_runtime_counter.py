"""Native model lifetime accounting and restart checkpoint regression tests."""
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from payload.m300_nvm import HostNVM
from payload.m300_runtime import CHECKPOINT_SECONDS
from test_native_reprint import replay_session, finish
from test_settings_information import session


def native_model(h):
    (h.files / 'counter.gcode').write_text('G90\n')
    h.hotend.temperature = 240.
    h.run('SDCARD_PRINT_FILE FILENAME="counter.gcode"')
    h.vsd.print_stats.note_start()


def deposit(h):
    h.vsd.cmd_from_sd = True
    try:
        h.run('G1 X100 Y110 E20 F3600')
    finally:
        h.vsd.cmd_from_sd = False


class RuntimeCounterTests(unittest.TestCase):
    def test_native_start_pause_resume_end_excludes_nonmodel_phases(self):
        def heater_wait(h):
            h.now += 40.
            h.nvm._save_runtime(h.now)

        with replay_session(heater_wait) as h:
            native_model(h)
            h.now += 300.
            h.run('G1 X110 E19')  # Non-SD service/console move.
            h.now += 30.
            deposit(h)
            h.now += 50.
            h.vsd.print_stats.note_pause()
            h.busy_until = h.now + 2.
            h.now += 100.
            h.nvm._save_runtime(h.now)
            h.vsd.print_stats.note_start()
            h.now += 10.
            h.busy_until = h.now + 2.
            h.vsd.cmd_from_sd = True
            h.run('M109 S240')
            h.vsd.cmd_from_sd = False
            h.now += 20.
            h.busy_until = h.now
            h.models.runtime_end()
            h.vsd.print_stats.note_start()  # Worker resumes for final EOF.
            h.now += 50.
            finish(h)
            h.nvm._save_runtime(h.now)
            self.assertEqual(h.nvm.ui_snapshot()['counters'],
                             {'completed_jobs': 1, 'print_seconds': 84.})

    def test_cancelled_model_keeps_time_without_marking_a_completion(self):
        with replay_session() as h:
            checkpoints = []
            h.handlers['m300:runtime_checkpoint'].append(
                lambda: checkpoints.append(h.nvm.ui_snapshot()['counters']['print_seconds']))
            native_model(h)
            deposit(h)
            h.now += 15.
            h.nvm._save_runtime(h.now)
            self.assertEqual(checkpoints, [])
            h.now += 27.5
            h.busy_until = h.now
            h.vsd.print_stats.note_cancel()
            h.nvm._save_runtime(h.now)
            self.assertEqual(h.nvm.ui_snapshot()['counters'],
                             {'completed_jobs': 0, 'print_seconds': 42.5})
            self.assertEqual(checkpoints, [42.5])

    def test_cancel_before_deposition_keeps_no_print_time(self):
        with replay_session() as h:
            native_model(h)
            h.now += 380.
            h.vsd.print_stats.note_cancel()
            h.nvm._save_runtime(h.now)
            self.assertEqual(h.nvm.ui_snapshot()['counters']['print_seconds'], 0.)

    def test_power_loss_checkpoint_and_disconnect_preserve_prior_job_time(self):
        with replay_session() as h:
            native_model(h)
            deposit(h)
            path = Path(h.nvm.store.path)
            h.now += CHECKPOINT_SECONDS
            h.nvm._save_runtime(h.now)
            reopened = HostNVM(path, **h.nvm.store.identity)
            self.assertEqual(reopened.snapshot()['counters']['print_seconds'], CHECKPOINT_SECONDS)
            h.now += 4.5
            h.emit('klippy:disconnect')
            reopened = HostNVM(path, **h.nvm.store.identity)
            self.assertEqual(reopened.snapshot()['counters']['print_seconds'], CHECKPOINT_SECONDS + 4.5)

    def test_retry_after_published_checkpoint_does_not_duplicate_seconds(self):
        with session() as h:
            nvm = h.nvm
            nvm.runtime_start(h.now)
            h.now += 20.
            real_update = nvm.store.update

            def lose_confirmation(mutate):
                real_update(mutate)
                raise OSError('injected post-replace failure')

            nvm.store.update = lose_confirmation
            nvm._save_runtime(h.now)
            self.assertIn('injected', nvm.runtime_error)
            nvm.store.update = real_update
            h.now += 12.
            nvm.runtime_pause(h.now, drain=False)
            nvm._save_runtime(h.now)
            nvm._save_runtime(h.now)
            self.assertEqual(nvm.ui_snapshot()['counters']['print_seconds'], 32.)

    def test_information_displays_only_unsynced_seconds_in_addition_to_factory(self):
        with session() as h:
            h.nvm.record_completed_job(200.)
            h.board.hardware = NS(get_status=lambda: dict(serial_number='Z12345678',
                                  factory_print_minutes=122, factory_counter_committed_seconds=120.))
            info = h.settings.information(h.now)
            self.assertEqual(info['klipper_print_seconds'], 200.)
            self.assertEqual(info['klipper_unsynced_print_seconds'], 80.)
            self.assertEqual(info['total_print_seconds'], 7400.)
