# SPDX-License-Identifier: GPL-3.0-or-later
# Marcin Kowalik <mkowalik@agh.edu.pl>
# m300_oled_idle.py - Przechowuje czasy DIM i SLEEP na hoście i uzgadnia obie wartości z pamięcią MCU.
"""Operator-selected OLED thresholds. The factory counter is independent."""
import json
from secrets import randbits

KEYS = ('oled_dim_minutes', 'oled_sleep_minutes')
STATE = 'm300_oled_idle_state token=%u status=%c dim=%c sleep=%c serial=%u'


def valid(dim, sleep):
    return type(dim) is int and type(sleep) is int and 1 <= dim <= sleep <= 60


def valid_preference(dim, sleep):
    return all(type(n) is int and 1 <= n <= 60 for n in (dim, sleep))


def effective(pair):
    return min(pair), pair[1]


class OledTimers:
    def __init__(self, display):
        self.display = display
        self.printer = display.printer
        self.reactor = display.reactor
        self.token = randbits(32)
        self.read = self.write = self.mcu = None
        self.serial = None
        self.status = 'STARTING'
        self.desired = self.observed = None
        self.applied_preference = None
        self.mirror_has_preference_mcu = False
        self.preference_mcu = False
        self.saving = False
        self.mirror = None
        self.error = None
        self.timer = self.reactor.register_timer(self.sync)

    def start(self):
        self.board = self.printer.lookup_object('m300_mcu', None)
        self.nvm = self.printer.lookup_object('m300_nvm', None)
        if self.board is None or self.nvm is None:
            self.status = 'UNAVAILABLE'
            return
        self.mcu = self.board.get_mcu()
        if self.mcu.is_fileoutput():
            self.status = 'FILEOUTPUT'
            return
        if self.mcu.get_constants().get('M300_OLED_IDLE_ABI') != 1:
            self.status = 'MCU_UPDATE_REQUIRED'
            return
        self.preference_mcu = self.mcu.get_constants().get('M300_OLED_PREF_ABI') == 1
        prefix = 'm300_oled_pref' if self.preference_mcu else 'm300_oled_idle'
        self.read = self.mcu.lookup_query_command(prefix + '_query token=%u', STATE)
        self.write = self.mcu.lookup_query_command(
            prefix + '_store token=%u dim=%c sleep=%c deadline=%u', STATE)
        self.reactor.update_timer(self.timer, self.reactor.monotonic() + 1.)

    def stop(self):
        self.status = 'DISCONNECTED'
        self.applied_preference = None
        self.serial = self.observed = self.desired = self.mirror = None
        self.read = self.write = None
        self.reactor.update_timer(self.timer, self.reactor.NEVER)

    def pair(self):
        d = self.display
        return tuple(max(1, min(60, round(seconds / 60))) for seconds in
                     (d.timeout, d.sleep_timeout))

    def preferences(self):
        return self.desired or (self.applied_preference or self.pair()[0], self.pair()[1])

    def apply(self, pair):
        previous = self.pair()
        old_preference = self.applied_preference
        self.applied_preference = pair[0]
        pair = effective(pair)
        self.display.timeout, self.display.sleep_timeout = (n * 60 for n in pair)
        for key, old, new in zip(KEYS, previous, pair):
            if old != new or (key == KEYS[0] and old_preference is not None
                              and old_preference != self.applied_preference):
                self.printer.send_event('m300:setting_changed', key, new)

    def path(self):
        return self.nvm.store.path + '.oled-idle'

    def load(self, serial):
        try:
            with open(self.path(), 'rb') as stream:
                record = json.loads(stream.read(1025))
        except FileNotFoundError:
            return None
        if record['serial'] != serial:
            return None
        pair = (record['dim'], record['sleep'])
        if not valid(*pair):
            raise ValueError('Invalid saved OLED timers')
        if type(record['pending']) is not bool:
            raise ValueError('Invalid OLED timer receipt')
        preferred = record.get('preferred_dim', pair[0])
        raw = (preferred, pair[1])
        if not valid_preference(*raw) or effective(raw) != pair:
            raise ValueError('Invalid saved OLED preference')
        self.mirror_has_preference_mcu = record.get('preference_mcu') is True
        return raw, record['pending']

    def remember(self, serial, pair, pending):
        raw = json.dumps(dict(serial=serial, dim=min(pair), preferred_dim=pair[0], sleep=pair[1],
                              pending=pending, preference_mcu=self.preference_mcu)).encode()
        self.nvm.executor.submit(self.nvm.store._atomic_replace, self.path(), raw)
        self.mirror_has_preference_mcu = self.preference_mcu
        self.mirror = (pair, pending)

    def select(self, dim, sleep):
        if not valid_preference(dim, sleep):
            raise self.printer.command_error('Use 1 to 60 minutes for each OLED timer')
        if not self.serial or not self.write or self.saving:
            raise self.printer.command_error('OLED timer storage unavailable: ' + self.status)
        pair = (dim, sleep)
        if pair == self.desired and self.status in ('SYNCED', 'PENDING'):
            return
        serial = self.serial
        self.saving = True
        try:
            self.remember(serial, pair, True)
            if serial != self.serial:
                raise self.printer.command_error('MCU disconnected while saving OLED timers')
            self.desired = pair
            self.apply(pair)
            self.display.activity('oled_timers')
            self.status = 'PENDING'
            self.reactor.update_timer(self.timer, self.reactor.monotonic() + .2)
        finally:
            self.saving = False

    def sync(self, now):
        if not self.read:
            return self.reactor.NEVER
        try:
            self.token = (self.token + 1) & 0xffffffff
            token = self.token
            target = self.desired
            if target and not self.preference_mcu:
                target = effective(target)
            if self.serial and target and target != self.observed:
                mutex = self.display.gcode.get_mutex()
                if mutex.test():
                    return now + 2.
                with mutex:
                    if self.board.hardware._counter_blocker(self.nvm, now):
                        return now + 2.
                    deadline = self.mcu.print_time_to_clock(
                        self.mcu.estimated_print_time(self.reactor.monotonic()) + .35)
                    packet = self.write.send([token, *target, deadline & 0xffffffff])
            else:
                packet = self.read.send([token])
            if not self.read:
                return self.reactor.NEVER
            if packet['token'] != token:
                raise ValueError('Stale MCU OLED timer reply')
            serial = packet['serial']
            code = packet['status']
            if code in (3, 4):
                self.status = 'FLASH_ERROR' if code == 3 else 'UNSUPPORTED_TARGET'
                self.error = self.status
                return self.reactor.NEVER
            if code == 2:
                self.status = 'PENDING'
                return now + 2.
            if code not in (0, 1) or not serial:
                raise ValueError('Invalid MCU OLED timer reply')
            observed = None if code == 0 else (packet['dim'], packet['sleep'])
            validate = valid_preference if self.preference_mcu else valid
            if observed is not None and not validate(*observed):
                raise ValueError('Invalid MCU OLED timer values')
            if self.serial is None:
                mirror = self.nvm.executor.submit(self.load, serial)
                if not self.read:
                    return self.reactor.NEVER
                self.mirror = mirror
                self.desired = observed
                if mirror and (mirror[1] or not observed or (
                        not self.mirror_has_preference_mcu and effective(mirror[0]) == observed)):
                    self.desired = mirror[0]
                self.serial = serial
            elif self.serial != serial:
                raise ValueError('MCU identity changed')
            self.observed = observed
            if self.desired:
                self.apply(self.desired)
            self.error = None
            target = self.desired
            if target and not self.preference_mcu:
                target = effective(target)
            if target != observed:
                self.status = 'PENDING'
                return now + 2.
            if observed and (self.mirror != (self.desired, False)
                             or self.mirror_has_preference_mcu != self.preference_mcu):
                if self.saving:
                    return now + 2.
                self.saving = True
                try:
                    self.remember(serial, self.desired, False)
                finally:
                    self.saving = False
            self.status = 'SYNCED' if observed else 'DEFAULT'
            return self.reactor.NEVER
        except Exception as exc:
            self.status, self.error = 'READ_ERROR', str(exc)
            return self.reactor.monotonic() + 10. if self.read else self.reactor.NEVER
