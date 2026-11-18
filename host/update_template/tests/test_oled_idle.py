# SPDX-License-Identifier: GPL-3.0-or-later
# Marcin Kowalik <mkowalik@agh.edu.pl>
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock

from payload.m300_oled_idle import OledTimers, valid


class OledTimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = SimpleNamespace(timeout=300, sleep_timeout=300, printer=Mock(),
                                 reactor=Mock(), activity=Mock(), gcode=Mock())
        self.d.printer.command_error = ValueError
        self.d.reactor.NEVER = 99999
        self.d.reactor.monotonic.return_value = 5.
        self.t = OledTimers(self.d)
        self.t.nvm = Mock()
        self.t.nvm.executor.submit.side_effect = lambda fn,*args: fn(*args)
        self.t.nvm.store.path = self.tmp.name + '/config'
        self.t.nvm.store._atomic_replace.side_effect = lambda path,raw: Path(path).write_bytes(raw)
        self.t.read = Mock()
        self.t.write = Mock()
        self.t.read.send.side_effect = lambda args: self.reply(args, (4, 12))
        self.t.write.send.side_effect = lambda args: self.reply(args, tuple(args[1:3]))
        self.d.gcode.get_mutex.return_value = MagicMock()
        self.d.gcode.get_mutex.return_value.test.return_value = False
        self.t.board = Mock()
        self.t.board.hardware._counter_blocker.return_value = None
        self.t.mcu = Mock()
        self.t.mcu.estimated_print_time.return_value = 4
        self.t.mcu.print_time_to_clock.return_value = 1000

    def reply(self, args, pair):
        return dict(token=args[0], status=1, dim=pair[0], sleep=pair[1], serial=100)

    def test_cold_read_and_no_writes(self):
        self.assertEqual(self.t.sync(5.), self.d.reactor.NEVER)
        self.assertEqual(self.t.pair(), (4, 12))
        self.assertEqual(self.t.status, 'SYNCED')
        self.t.write.send.assert_not_called()

    def test_pair_is_durable_before_flash_and_restored_after_host_restart(self):
        self.t.sync(5.)
        self.t.select(12, 60)
        self.assertEqual(self.t.load(100), ((12, 60), True))
        self.assertIsNone(self.t.load(99))
        self.t.serial = self.t.desired = self.t.observed = None
        self.t.sync(6.)
        self.assertEqual(self.t.status, 'PENDING')
        self.t.board.hardware._counter_blocker.return_value = 'printing'
        self.t.sync(7.)
        self.t.write.send.assert_not_called()
        self.t.board.hardware._counter_blocker.return_value = None
        self.t.sync(8.)
        self.assertEqual(self.t.observed, (12, 60))
        self.assertEqual(self.t.status, 'SYNCED')

    def test_confirmed_old_host_mirror_does_not_replace_newer_board_values(self):
        self.t.remember(100, (2, 20), False)
        self.t.sync(5.)
        self.assertEqual(self.t.load(100), ((4, 12), False))
        self.t.write.send.assert_not_called()

    def test_deadline_deferral_and_invalid_ranges(self):
        for pair in ((0,1),(1,61),(15,5),(True,2)):
            self.assertFalse(valid(*pair))
        self.t.sync(5.)
        self.t.select(1,1)
        self.t.write.send.side_effect = lambda a: dict(self.reply(a,(4,12)),status=2)
        self.t.sync(6.)
        self.assertEqual(self.t.status,'PENDING')
        self.assertEqual(self.t.observed,(4,12))

    def test_broken_mirror_is_reported_and_never_written_to_board(self):
        Path(self.t.path()).write_text(json.dumps(dict(serial=100,dim=30,sleep=10)))
        self.t.sync(5.)
        self.assertEqual(self.t.status,'READ_ERROR')
        self.t.write.send.assert_not_called()
