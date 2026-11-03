"""Verified EOF, native start delegation and immutable replay lifecycle."""
from contextlib import contextmanager
from types import SimpleNamespace as NS
import unittest

from payload.m300_models import ModelError
from test_native_models import model_session, prepare


@contextmanager
def replay_session():
    with model_session() as h:
        sd = h.vsd
        stats = sd.print_stats
        stats.state = 'standby'
        stats.filename = ''
        sd.cmd_from_sd = sd.must_pause_work = False

        def set_file(name):
            stats.filename, stats.state = name, 'standby'

        def load(gcmd, filename, check_subdirs=False):
            sd.current_file = (h.files / filename).open(encoding='utf-8', newline='')
            sd.file_size = (h.files / filename).stat().st_size
            sd.file_position = 0
            stats.set_current_file(filename)

        def reset():
            if sd.current_file is not None:
                sd.current_file.close()
            sd.current_file = sd.work_timer = None
            stats.set_current_file('')
            h.emit('virtual_sdcard:reset_file')

        def print_file(gcmd):
            reset()
            sd._load_file(gcmd, gcmd.get('FILENAME'), check_subdirs=True)
            sd.do_resume()

        stats.set_current_file = set_file
        stats.note_complete = lambda: setattr(stats, 'state', 'complete')
        stats.note_pause = lambda: setattr(stats, 'state', 'paused')
        sd._load_file = load
        sd._reset_file = reset
        h.gcode.register_command('SDCARD_PRINT_FILE', print_file)
        h.models._ready()
        yield h


def finish(h, read_all=True):
    sd = h.vsd
    stream = sd.current_file
    stream.seek(sd.file_position)
    data = stream.read(8192)
    sd.file_position += len(data.encode('utf-8'))
    if read_all:
        assert not stream.read(8192)
    stream.close()
    sd.current_file = sd.work_timer = None
    sd.print_stats.note_complete()
    return data


class NativeReprintTests(unittest.TestCase):
    def test_physical_job_replays_same_bytes_and_uses_single_use_tokens(self):
        with replay_session() as h:
            h.models.start(prepare(h))
            native_name = h.vsd.print_stats.filename
            self.assertRegex(native_name, r'^sd:/[a-f0-9]{32}/part\.zcode$')
            first = finish(h)
            bus_count = len(h.image.bus)
            h.image.sectors.clear()
            view = h.models.reprint_status(h.now)
            self.assertTrue(view['available'])
            self.assertEqual(view['filename'], 'sd:/part.zcode')
            self.assertEqual(h.models.reprint(view['token']), view['filename'])
            self.assertFalse(h.models.reprint_status(h.now)['available'])
            self.assertEqual(h.vsd.file_position, 0)
            self.assertEqual(h.vsd.print_stats.filename, native_name)
            self.assertEqual(finish(h), first)
            self.assertEqual(len(h.image.bus), bus_count)
            with self.assertRaisesRegex(ModelError, 'No completed'):
                h.models.reprint(view['token'])

    def test_fluidd_physical_dispatch_binds_to_snapshot_alias(self):
        with replay_session() as h:
            h.models.start(prepare(h))
            old_name = h.vsd.print_stats.filename
            finish(h)
            h.run('SDCARD_PRINT_FILE FILENAME="%s"' % old_name)
            finish(h)
            # Importing the same card path makes a new snapshot identity.
            h.models.start(prepare(h))
            new_name = h.vsd.print_stats.filename
            finish(h)
            self.assertNotEqual(new_name, old_name)
            for name in (old_name, 'sd:/part.zcode'):
                with self.assertRaisesRegex(h.printer.command_error, 'No matching'):
                    h.run('SDCARD_PRINT_FILE FILENAME="%s"' % name)
            self.assertIsNone(h.vsd.current_file)
            self.assertEqual(h.vsd.print_stats.filename, new_name)

    def test_regular_fluidd_file_retains_exact_opened_bytes_without_alias(self):
        with replay_session() as h:
            path = h.files / 'normal print.gcode'
            source = 'G90\r\nM105\r\n'
            path.write_bytes(source.encode())
            h.run('SDCARD_PRINT_FILE FILENAME="normal print.gcode"')
            self.assertEqual(h.vsd.print_stats.filename, path.name)
            self.assertEqual(finish(h), source)
            path.write_bytes(b'G91\n')
            token = h.models.reprint_status(h.now)['token']
            self.assertEqual(h.models.reprint(token), path.name)
            self.assertEqual(finish(h), source)
            # A new regular Fluidd start has native filename semantics.
            h.run('SDCARD_PRINT_FILE FILENAME="normal print.gcode"')
            self.assertEqual(finish(h), 'G91\n')

    def test_expired_token_cannot_start_while_motion_is_queued(self):
        with replay_session() as h:
            h.models.start(prepare(h))
            finish(h)
            token = h.models.reprint_status(h.now)['token']
            h.busy_until = h.now + 10.
            self.assertFalse(h.models.reprint_status(h.now)['available'])
            with self.assertRaisesRegex(ModelError, 'No completed'):
                h.models.reprint(token)
            self.assertIsNone(h.vsd.current_file)
            h.now += 11.
            self.assertEqual(h.models.reprint_status(h.now)['token'], token)

    def test_cancel_error_and_premature_eof_never_enable_repeat(self):
        for reason in ('cancelled', 'error', 'incomplete'):
            with self.subTest(reason=reason), replay_session() as h:
                h.models.start(prepare(h))
                sd = h.vsd
                stream = sd.current_file
                if reason == 'incomplete':
                    finish(h, read_all=False)
                else:
                    stream.seek(0)
                    stream.read(8)
                    stream.close()
                    sd.current_file = sd.work_timer = None
                    sd.print_stats.state = reason
                    h.models._record_complete()
                self.assertTrue(stream.closed)
                self.assertFalse(h.models.reprint_status(h.now)['available'])
                self.assertIsNone(h.models.completed)

    def test_native_pause_resume_can_finish_but_skipped_position_cannot(self):
        for skip in (False, True):
            with self.subTest(skip=skip), replay_session() as h:
                h.models.start(prepare(h))
                sd = h.vsd
                sd.current_file.seek(0)
                sd.file_position = len(sd.current_file.read(8).encode())
                sd.work_timer = None
                sd.print_stats.note_pause()
                self.assertFalse(h.models.reprint_status(h.now)['available'])
                if skip:
                    sd.file_position += 1  # M26 or an external file-position jump.
                sd.do_resume()
                finish(h)
                self.assertEqual(h.models.reprint_status(h.now)['available'], not skip)

    def test_clear_file_and_restart_discard_completed_snapshots(self):
        for event in ('virtual_sdcard:reset_file', 'klippy:shutdown', 'gcode:request_restart'):
            with self.subTest(event=event), replay_session() as h:
                h.models.start(prepare(h))
                finish(h)
                stream = h.models.completed.stream
                h.emit(event)
                self.assertTrue(stream.closed)
                self.assertFalse(h.models.reprint_status(h.now)['available'])

    def test_sd_worker_cannot_use_completed_alias_as_a_reprint_command(self):
        with replay_session() as h:
            h.models.start(prepare(h))
            filename = h.vsd.print_stats.filename
            finish(h)
            h.vsd.cmd_from_sd = True
            with self.assertRaisesRegex(h.printer.command_error, 'No matching'):
                h.run('SDCARD_PRINT_FILE FILENAME="%s"' % filename)
            self.assertIsNone(h.vsd.current_file)
