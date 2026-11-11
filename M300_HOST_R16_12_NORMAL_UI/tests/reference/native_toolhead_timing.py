# SPDX-License-Identifier: GPL-3.0-only
# Exact ToolHead timing methods from Klipper ee2c6fb6b00b2b5d097ef70d0868df7d74943b51.
# Copyright Kevin O'Connor; reference only, never installed in the printer.
# Surrounding motion/clock hardware is supplied by the regression harness.
BUFFER_TIME_START = 0.250
BUFFER_TIME_HIGH = 1.0

class ToolHeadTiming:
    def _calc_print_time(self):
        curtime = self.reactor.monotonic()
        est_print_time = self.mcu.estimated_print_time(curtime)
        kin_time = self.motion_queuing.calc_step_gen_restart(est_print_time)
        min_print_time = max(est_print_time + BUFFER_TIME_START, kin_time)
        if min_print_time > self.print_time:
            self.print_time = min_print_time
            self.printer.send_event("toolhead:sync_print_time",
                                    curtime, est_print_time, self.print_time)

    def _flush_lookahead(self, is_runout=False):
        # Transit from "NeedPrime"/"Priming"/main state to "NeedPrime"
        prev_print_time = self.print_time
        self._process_lookahead()
        self.special_queuing_state = "NeedPrime"
        self.need_check_pause = -1.
        self.lookahead.set_flush_time(BUFFER_TIME_HIGH)
        self.check_stall_time = 0.
        if is_runout and prev_print_time != self.print_time:
            self.check_stall_time = self.print_time

    def get_last_move_time(self):
        if self.special_queuing_state:
            self._flush_lookahead()
            self._calc_print_time()
        else:
            self._process_lookahead()
        return self.print_time

    def check_busy(self, eventtime):
        est_print_time = self.mcu.estimated_print_time(eventtime)
        return self.print_time, est_print_time, self.lookahead.is_empty()
