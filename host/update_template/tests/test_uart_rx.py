"""UART RX diagnostics do not synthesize data or add polling."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from payload.m300_mcu import M300MCU


class UartRxTests(unittest.TestCase):
    def setUp(self):
        self.board = M300MCU.__new__(M300MCU)
        self.board.connected = True
        self.board.mcu = SimpleNamespace(is_fileoutput=Mock(return_value=False))
        self.board._uart_rx_query = Mock()
        self.board.gcode = Mock()
        self.board.reactor = Mock()
        self.gcmd = Mock()

    def test_manual_request_is_nonblocking_and_reply_is_reported(self):
        self.board.cmd_uart_rx_status(self.gcmd)
        self.board._uart_rx_query.send.assert_called_once_with()
        self.board._handle_uart_rx(dict(clock=13, overrun=2, framing=0,
                                        noise=1, buffer_drops=0))
        self.board.gcode.respond_info.assert_not_called()
        callback, = self.board.reactor.register_async_callback.call_args.args
        callback(1.)
        self.board.gcode.respond_info.assert_called_once_with(
            'M300_UART_RX {"buffer_drops": 0, "clock": 13, "framing": 0, "noise": 1, "overrun": 2}')

    def test_old_firmware_and_fileoutput_never_produce_counters(self):
        query = self.board._uart_rx_query
        self.board.mcu.is_fileoutput.return_value = True
        self.board.cmd_uart_rx_status(self.gcmd)
        self.gcmd.respond_info.assert_called_once_with(
            'M300 UART RX counters require a live MCU connection')
        self.gcmd.reset_mock()
        self.board._uart_rx_query = None
        self.board.cmd_uart_rx_status(self.gcmd)
        self.gcmd.respond_info.assert_called_once_with(
            'M300 UART RX counters require MCU diagnostic firmware')
        query.send.assert_not_called()

    def test_shutdown_queries_guard_and_counters_without_rearming(self):
        self.board._handle_stop = Mock()
        self.board._query_cmd = Mock()
        self.board._arm_cmd = Mock()
        self.board._handle_shutdown()
        self.board._handle_stop.assert_called_once_with()
        self.board._query_cmd.send.assert_called_once_with()
        self.board._uart_rx_query.send.assert_called_once_with()
        self.board._arm_cmd.send.assert_not_called()
