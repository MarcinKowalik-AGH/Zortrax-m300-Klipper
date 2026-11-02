# SPDX-License-Identifier: GPL-3.0-or-later
"""M10 OLED link supervisory facade. Optional: no pins, motion or menu owner.

[M300 OLED] retains the sole MCU queue, SSD1322 renderer and encoder.
Omission of [m300_oled_link] restores the exact M09 transport policy.
"""
import json
from .m300_oled_link_state import OledLinkPolicy


class M300OledLink:
    def __init__(self, config):
        if not config.has_section('m300_oled'):
            raise config.error('M10 requires [m300_oled] section')
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.oled = self.printer.load_object(config, 'm300_oled')
        self.policy = OledLinkPolicy(
            retry_delay=config.getfloat('retry_delay', 1.5, minval=.2, maxval=30.),
            max_retries=config.getint('max_retries', 2, minval=0, maxval=5),
            automatic=config.getboolean('automatic', True))
        self.printer.lookup_object('gcode').register_command(
            'ZORTRAX_OLED_LINK_STATUS', self.cmd_status, when_not_ready=True)

    def on_ready(self, now):
        self.policy.ready(now)

    def on_stop(self):
        self.policy.stop()

    def on_manual(self, now):
        self.policy.manual(now)

    def on_timeout(self, now, reason):
        self.policy.fault(now, reason)

    def service(self, now):
        return self.policy.service(now, self.oled.stream,
                                   self.oled.connected,
                                   update_frame=self.oled._render)

    def get_status(self, now):
        return self.policy.status(now, self.oled.stream, self.oled.connected)

    def menu_rows(self, now):
        s = self.get_status(now)
        return 'M10: OLED link', [
            ('Back', 'oled_link_back'),
            ('Reinitialize full display', 'oled_link_reinit'),
            ('State: ' + s['state'], None),
            ('Frame ready: ' + str(s['display_ready']), None),
            ('ACK pending: ' + str(s['pending_ack']), None),
            ('Retries: %d/%d' % (s['retries_used'], s['max_retries']), None),
            ('Frames: ' + str(s['completed_frames']), None),
            ('Error: ' + str(s['last_error'] or '-'), None)]

    def cmd_status(self, gcmd):
        gcmd.respond_info('M300_M10 ' + json.dumps(
            self.get_status(self.reactor.monotonic()), sort_keys=True))


def load_config(config):
    return M300OledLink(config)
