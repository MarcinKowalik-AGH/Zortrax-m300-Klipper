# SPDX-License-Identifier: GPL-3.0-or-later
"""M300 SSD1322 transactions; one ACK-paced command and two bounded frames.

The controller sequence is from M300 1.3.1 D_OLED_initialization_wire.json,
including its custom B8 greyscale table and 16384-byte clear. Reset delays
are conservative integration values, NOT measured stock loop durations.
"""

import itertools
from collections import deque

INIT = (
    (0xfd, b'\x12'), (0xae, b''), (0xb3, b'\x91'),
    (0xca, b'\x3f'), (0xa2, b'\x00'), (0xa1, b'\x00'),
    (0xa0, b'\x14\x11'), (0xb5, b'\x00'), (0xab, b'\x01'),
    (0xb4, b'\xa0\xfd'), (0xc1, b'\x9f'), (0xc7, b'\x0f'),
    (0xb8, bytes(range(12, 181, 12))), (0x00, b''), (0xb1, b'\xe2'),
    (0xd1, b'\xa2\x20'), (0xbb, b'\x1f'), (0xb6, b'\x08'),
    (0xbe, b'\x07'), (0xa6, b''), (0xa9, b''),
)
MAX_DIRTY_REGIONS = 16
FAST_TX_OVERHEAD = 20  # Conservative native framing and burst command fields.
FAST_ACK_OVERHEAD = 10  # Framing, response ID and OLED acknowledgement token.


def command(cmd, data=b'', delay=0.):
    yield ('write', (0, bytes([cmd])), delay if not data else 0.)
    if data:
        yield ('write', (1, bytes(data)), delay)


def frame_operations(wire, first_row=0, last_row=63, first_col=0, last_col=63):
    """Stream an SSD1322 rectangle in its 4-pixel-wide column address units.

    One SSD1322 column address is TWO packed wire bytes (4 pixels). Each
    row's data are concatenated in row order without changing nibble order.
    Full-screen defaults preserve the TEST01 init byte stream exactly.
    """
    if (len(wire)!=8192 or not 0<=first_row<=last_row<64 or
            not 0<=first_col<=last_col<64):
        raise ValueError('Invalid OLED frame/window')
    yield from command(0x15,bytes([0x1c+first_col,0x1c+last_col]))
    yield from command(0x75,bytes([first_row,last_row]))
    yield from command(0x5c)
    start=first_col*2
    stop=(last_col+1)*2
    # Keep the same <=32-byte transport contract as ABI2.
    packed=b''.join(wire[y*128+start:y*128+stop]
                    for y in range(first_row,last_row+1))
    for offset in range(0,len(packed),32):
        yield ('write',(1,packed[offset:offset+32]),0.0)


def diff_window(before,after):
    """Return minimal rectangular changed area, aligned to 4-pixel columns.

    None means no change. Input is SSD1322 row-major packed 4bpp, 8192B.
    The bounding rectangle may contain some unchanged pixels, which is safe;
    unlike the old implementation it does not resend the entire row width.
    """
    if len(before)!=8192 or len(after)!=8192:
        raise ValueError('Invalid OLED buffer for diff')
    lo_y=64;hi_y=-1;lo_col=64;hi_col=-1
    for y in range(64):
        start=y*128
        if before[start:start+128]==after[start:start+128]:
            continue
        lo_y=min(lo_y,y);hi_y=y
        for c in range(64):
            i=start+2*c
            if before[i:i+2]!=after[i:i+2]:
                lo_col=min(lo_col,c);hi_col=max(hi_col,c)
    if hi_y<0:
        return None
    return (lo_y,hi_y,lo_col,hi_col)



def _tiled_regions(before, after):
    """Find non-overlapping dirty rectangles in a grid of 32x8-pixel tiles."""
    # 8 column-address groups (32 visible px) by 8 row tiles; 64 tiles.
    tile_dirty=[[False]*8 for _ in range(8)]
    for ty in range(8):
        for tc in range(8):
            for y in range(ty*8,ty*8+8):
                off=y*128+tc*16
                if before[off:off+16]!=after[off:off+16]:
                    tile_dirty[ty][tc]=True
                    break
    # Coalesce horizontal runs on each tile row, then vertically merge runs
    # sharing precisely the same column span. No windows overlap.
    rects=[]
    active={}
    for ty in range(8):
        runs=[];c=0
        while c<8:
            if not tile_dirty[ty][c]:
                c+=1;continue
            start=c
            while c<8 and tile_dirty[ty][c]:c+=1
            runs.append((start,c-1))
        following={}
        for c0,c1 in runs:
            key=(c0,c1)
            if key in active:
                y0,_,_,_=active[key]
                following[key]=(y0,ty*8+7,c0*8,c1*8+7)
            else:
                following[key]=(ty*8,ty*8+7,c0*8,c1*8+7)
        rects.extend(w for key,w in active.items() if key not in following)
        active=following
    rects.extend(active.values())
    rects.sort(key=lambda w:(w[0],w[2]))
    return tuple(rects)


def _raw_window_cost(window):
    y0, y1, c0, c1 = window
    size = (y1-y0+1) * (c1-c0+1) * 2
    return 5 + (size+31)//32


def diff_regions(before, after, max_regions=MAX_DIRTY_REGIONS):
    """Choose between exact bounds and dirty tiles for the raw OLED stream."""
    if type(max_regions) is not int or not 1 <= max_regions <= 64:
        raise ValueError('Invalid maximum OLED dirty region count')
    bounding = diff_window(before, after)
    if bounding is None:
        return ()

    tiles = _tiled_regions(before, after)
    if len(tiles) > max_regions or sum(map(_raw_window_cost, tiles)) >= _raw_window_cost(bounding):
        return (bounding,)
    return tiles


def stock_init_operations():
    """Exact captured stock command/data bytes, including display-on.

    Used as a testable reference; runtime inserts its complete visible frame
    BEFORE display-on so a previous application image is never presented.
    """
    for cmd, data in INIT:
        yield from command(cmd, data)
    yield from command(0x15, b'\x00\x77')
    yield from command(0x75, b'\x00\x7f')
    yield from command(0x5c)
    for _ in range(16384 // 32):
        yield ('write', (1, bytes(32)), 0.)
    yield from command(0xaf)


def init_operations(wire):
    # A fresh lifecycle always blanks, resets, replaces visible RAM with a full
    # frame. Delays begin only after the MCU confirms each GPIO operation.
    yield ('control', (0, 0), .010)
    yield ('control', (0, 1), .500)
    yield ('control', (1, 1), .020)
    # Only the visible 256x64 RAM window is used. A complete fresh frame is
    # written before AF, so clearing 16KiB of invisible RAM first adds latency
    # without improving the visible image. Keep stock_init_operations as the
    # immutable full OEM reference for regression, not the runtime path.
    for cmd, data in INIT:
        yield from command(cmd, data)
    yield from frame_operations(wire)
    yield from command(0xaf, delay=.200)


class OledStream:
    def __init__(self, timeout=1., refresh_interval=.2):
        if not .1 <= timeout <= 10. or not .2 <= refresh_interval <= 10.:
            raise ValueError('Invalid OLED timeout/refresh interval')
        self.timeout = timeout
        self.refresh_interval = refresh_interval
        self.latest = bytes(8192)
        self.token = self.sent = self.acked = self.completed_frames = 0
        self.ignored_acks = 0
        self.enabled = self.ready = False
        self.state = 'stopped'
        self.failure = None
        self.previous = self.target = self.operations = self.pending = None
        self.ready_after = self.next_frame = 0.
        self.restart_requested = False
        self.urgent_refresh = False
        self.frame_started_at = self.last_frame_ms = None

    def request(self, wire, urgent=False):
        wire = bytes(wire)
        if len(wire) != 8192:
            raise ValueError('OLED frame must be 8192 bytes')
        if urgent and wire != self.previous:
            self.urgent_refresh = True
        self.latest = wire

    def _begin(self, now):
        self.enabled = True
        self.ready = False
        self.state = 'initializing'
        self.failure = None
        self.previous = None
        self.target = self.latest
        self.operations = iter(init_operations(self.target))
        self.pending = None
        self.ready_after = self.next_frame = now
        self.restart_requested = False
        self.urgent_refresh = False
        self.frame_started_at = now

    def start(self, now):
        # A reinit requested during a transaction does not forget its ACK.
        # Finish that one command, then reset and send a complete new image.
        if self.enabled and self.pending is not None:
            self.restart_requested = True
            self.ready = False
            self.state = 'reinitializing'
        else:
            self._begin(now)

    def stop(self, reason=None, state='stopped'):
        self.enabled = self.ready = False
        self.state = state
        self.failure = str(reason) if reason else None
        self.operations = self.pending = self.previous = self.target = None
        self.restart_requested = False
        self.urgent_refresh = False

    def ack(self, token, now):
        if not self.enabled or self.pending is None or self.pending[0] != token:
            self.ignored_acks += 1
            return False
        self.ready_after = now + self.pending[2]
        self.pending = None
        self.acked += 1
        return True

    def step(self, now):
        if not self.enabled:
            return None
        if self.pending is not None:
            if now >= self.pending[1]:
                self.stop('OLED MCU acknowledgement timeout', 'fault')
                raise TimeoutError(self.failure)
            return None
        if now < self.ready_after:
            return None
        if self.restart_requested:
            self._begin(now)
        if self.operations is None:
            if self.previous == self.latest:
                self.urgent_refresh = False
                return None
            if now < self.next_frame and not self.urgent_refresh:
                return None
            self.target = self.latest
            self.frame_started_at = now
            regions = ((0,63,0,63),) if self.previous is None else diff_regions(self.previous, self.target)
            if not regions:
                return None
            self.operations = itertools.chain.from_iterable(
                frame_operations(self.target, *window) for window in regions)
        try:
            kind, args, delay = next(self.operations)
        except StopIteration:
            self.operations = None
            self.previous = self.target
            self.ready = True
            self.state = 'ready'
            self.completed_frames += 1
            self.last_frame_ms = 1000. * (now - self.frame_started_at)
            # Keep a navigation request received during the transfer until
            # its newest image has actually completed, as in Inventure RC6.
            if self.previous == self.latest:
                self.urgent_refresh = False
            self.next_frame = now + self.refresh_interval
            return None
        self.token = (self.token + 1) & 65535
        self.pending = (self.token, now + self.timeout, delay)
        self.sent += 1
        return kind, self.token, args


def rle_encode(data):
    """Lossless byte PackBits, preserving every SSD1322 grey-level nibble."""
    data = bytes(data)
    out = bytearray()
    i = 0
    while i < len(data):
        run = 1
        while i+run < len(data) and run < 128 and data[i+run] == data[i]:
            run += 1
        if run >= 3:
            out.extend((128 | (run-1), data[i])); i += run
            continue
        start = i
        i += run
        while i < len(data) and i-start < 128:
            if i+2 < len(data) and data[i] == data[i+1] == data[i+2]:
                break
            i += 1
        out.append(i-start-1)
        out.extend(data[start:i])
    return bytes(out)


def fast_blocks(data, dc=1):
    """<=32 encoded bytes, <=256 decoded bytes; entropy falls back to raw.

    One bounded pass fills each encoded packet, avoiding repeated compression
    of ever-shorter prefixes on the Orange Pi. High entropy uses 32 raw bytes.
    """
    data = bytes(data)
    offset = 0
    while offset < len(data):
        end = min(offset+256, len(data))
        i = offset
        encoded = bytearray()
        while i < end and len(encoded) <= 30:
            run = 1
            while i+run < end and run < 128 and data[i+run] == data[i]:
                run += 1
            if run >= 3:
                encoded.extend((128 | (run-1), data[i])); i += run
            else:
                start = i
                cap = min(end, i+31-len(encoded))
                while i < cap:
                    if i+2 < end and data[i] == data[i+1] == data[i+2]:
                        break
                    i += 1
                encoded.append(i-start-1)
                encoded.extend(data[start:i])
        count = i-offset
        encoded = bytes(encoded)
        if len(encoded) <= 32 and len(encoded)+2 < count:
            yield ('burst', (dc, 1, count, encoded), 0.)
            offset += count
        else:
            raw = data[offset:offset+32]
            yield ('burst', (dc, 0, len(raw), raw), 0.)
            offset += len(raw)


def fast_command(cmd, data=b'', delay=0.):
    yield ('burst', (0, 0, 1, bytes([cmd])), delay if not data else 0.)
    if data:
        yield ('burst', (1, 0, len(data), bytes(data)), delay)


def fast_frame_operations(wire, first_row=0, last_row=63, first_col=0, last_col=63):
    if (len(wire) != 8192 or not 0 <= first_row <= last_row < 64
            or not 0 <= first_col <= last_col < 64):
        raise ValueError('Invalid OLED frame/window')
    yield from fast_command(0x15, bytes([0x1c+first_col, 0x1c+last_col]))
    yield from fast_command(0x75, bytes([first_row, last_row]))
    yield from fast_command(0x5c)
    start, stop = first_col*2, (last_col+1)*2
    packed = b''.join(wire[y*128+start:y*128+stop]
                      for y in range(first_row, last_row+1))
    yield from fast_blocks(packed)


def _fast_update_operations(before, after):
    """Pick the cheaper encoded plan and reuse the blocks that were scored."""
    bounding = diff_window(before, after)
    if bounding is None:
        return iter(())
    tiles = _tiled_regions(before, after)
    if tiles == (bounding,) or len(tiles) > MAX_DIRTY_REGIONS:
        return fast_frame_operations(after, *bounding)

    first, second = (bounding,), tiles
    if sum(map(_raw_window_cost, tiles)) < _raw_window_cost(bounding):
        first, second = second, first
    overhead = FAST_TX_OVERHEAD + FAST_ACK_OVERHEAD
    first_ops = [op for window in first for op in fast_frame_operations(after, *window)]
    remaining = sum(len(args[3]) + overhead for _, args, _ in first_ops)
    second_ops = []
    for window in second:
        for op in fast_frame_operations(after, *window):
            remaining -= len(op[1][3]) + overhead
            if remaining <= 0:
                return iter(first_ops)
            second_ops.append(op)
    return iter(second_ops)


def fast_init_operations(wire):
    yield ('control', (0, 0), .010)
    yield ('control', (0, 1), .500)
    yield ('control', (1, 1), .020)
    for cmd, data in INIT:
        yield from fast_command(cmd, data)
    yield from fast_frame_operations(wire)
    yield from fast_command(0xaf, delay=.200)


class FastOledStream(OledStream):
    """Four ACK-bound DMA operations, two frame snapshots and one latest view.

    Control/delay operations are barriers. A frame commits only after *all*
    operations are ACKed in order. Reinit drains the old window before reset;
    timeout/stop discards it. Token allocation is monotonic across reinit.
    """
    def __init__(self, timeout=1., refresh_interval=.2, window=4,
                 interactive_interval=.020, work_interval=.100,
                 work_bytes_per_second=30000.):
        super().__init__(timeout, refresh_interval)
        if type(window) is not int or not 1 <= window <= 4:
            raise ValueError('OLED DMA window must be 1..4')
        if not .020 <= interactive_interval <= .200 or not .050 <= work_interval <= 1.:
            raise ValueError('Invalid interactive/work OLED interval')
        self.window = window
        self.interactive_interval = interactive_interval
        self.work_interval = work_interval
        if not 1. <= work_bytes_per_second <= 1000000.:
            raise ValueError('Invalid OLED work UART byte budget')
        self.work_bytes_per_second = work_bytes_per_second
        self.work_credit = 208.
        self.credit_at = self.budget_at = 0.
        self.active_work = False
        self.inflight = deque()
        self.exhausted = self.barrier = False
        self._held = None
        self._initializing = True
        self.next_interactive = 0.
        self.max_pending = self.coalesced_requests = self.payload_bytes = 0
        self.wire_bytes = self.last_payload_bytes = self.last_wire_bytes = 0
        self.frame_samples = deque(maxlen=128)
        self._frame_payload = self._frame_wire = 0

    def request(self, wire, urgent=False):
        if self.operations is not None and self.latest != wire and self.latest != self.target:
            self.coalesced_requests += 1
        super().request(wire, urgent)

    def _begin(self, now):
        super()._begin(now)
        self.inflight.clear()
        self.operations = iter(fast_init_operations(self.target))
        self.exhausted = self.barrier = False
        self._held = None
        self._initializing = True
        self._frame_payload, self._frame_wire = self.payload_bytes, self.wire_bytes

    def start(self, now):
        if self.state == 'reset_required':
            raise ValueError('OLED transaction uncertain; MCU reset required')
        if self.enabled and self.inflight:
            self.restart_requested = True
            self.ready = False
            self.state = 'reinitializing'
        else:
            self._begin(now)

    def stop(self, reason=None, state='stopped'):
        super().stop(reason, state)
        self.inflight.clear()
        self.exhausted = self.barrier = False
        self._held = None

    def ack(self, token, now):
        if not self.enabled or not self.inflight or self.inflight[0][0] != token:
            self.ignored_acks += 1
            return False
        _, _, delay = self.inflight.popleft()
        if delay:
            self.ready_after = now + delay
        self.pending = self.inflight[0] if self.inflight else None
        self.acked += 1
        return True

    def _commit(self, now):
        self.operations = None
        self.exhausted = False
        self.previous = self.target
        self.ready = True
        self.state = 'ready'
        self.completed_frames += 1
        self.last_frame_ms = 1000. * (now-self.frame_started_at)
        # Initialization includes conservative power/reset delays, so it is
        # explicitly excluded from steady-state latency statistics.
        if not self._initializing:
            self.frame_samples.append(self.last_frame_ms)
        self.last_payload_bytes = self.payload_bytes-self._frame_payload
        self.last_wire_bytes = self.wire_bytes-self._frame_wire
        if self.previous == self.latest:
            self.urgent_refresh = False
        self.next_frame = now+self.refresh_interval

    def step(self, now):
        if not self.enabled:
            return None
        if self.inflight and now >= self.inflight[0][1]:
            self.stop('OLED ACK timeout; MCU reset required', 'reset_required')
            raise TimeoutError(self.failure)
        if self.restart_requested:
            if self.inflight:
                return None
            self._begin(now)
        if now < self.ready_after:
            return None
        if self.barrier:
            if self.inflight:
                return None
            self.barrier = False
        if self.exhausted:
            if self.inflight:
                return None
            self._commit(now)
            return None
        if self.operations is None:
            if self.previous == self.latest:
                self.urgent_refresh = False
                return None
            if now < (self.next_interactive if self.urgent_refresh else self.next_frame):
                return None
            self.target = self.latest
            self._initializing = False
            self.frame_started_at = now
            self.next_interactive = now + (self.work_interval if self.active_work
                                          else self.interactive_interval)
            self._frame_payload, self._frame_wire = self.payload_bytes, self.wire_bytes
            self.operations = (fast_frame_operations(self.target) if self.previous is None
                               else _fast_update_operations(self.previous, self.target))
        if len(self.inflight) >= self.window:
            return None
        # Peek only one operation. A barrier cannot overtake older DMA data.
        if not hasattr(self, '_held') or self._held is None:
            try:
                self._held = next(self.operations)
            except StopIteration:
                self.exhausted = True
                if not self.inflight:
                    self._commit(now)
                return None
        kind, args, delay = self._held
        if (kind == 'control' or delay) and self.inflight:
            return None
        if self.active_work:
            # 20 bytes cover msg id, token, args, length and a whole native
            # serial packet's framing (verified against the real dictionary).
            cost = (len(args[3]) if kind == 'burst' else 0) + FAST_TX_OVERHEAD
            self.work_credit = min(208., self.work_credit + max(0., now-self.credit_at)*self.work_bytes_per_second)
            self.credit_at = now
            if cost > self.work_credit + 1.e-9:
                self.budget_at = now + (cost-self.work_credit)/self.work_bytes_per_second
                return None
            self.work_credit -= cost
            self.budget_at = now
        self._held = None
        self.barrier = kind == 'control' or bool(delay)
        self.token = (self.token+1) & 65535
        self.inflight.append((self.token, now+self.timeout, delay))
        self.pending = self.inflight[0]
        self.max_pending = max(self.max_pending, len(self.inflight))
        self.sent += 1
        if kind == 'burst':
            self.payload_bytes += len(args[3])
            self.wire_bytes += args[2]
        return kind, self.token, args

    def next_wakeup(self, now):
        if not self.enabled:
            return now+1.
        if self.inflight:
            return min(self.inflight[0][1], self.budget_at) if self._held is not None and self.budget_at > now else self.inflight[0][1]
        if self.ready_after > now:
            return self.ready_after
        if self.operations is not None or self.restart_requested:
            return max(now+.0001, self.budget_at) if self.active_work else now+.0001
        if self.previous != self.latest:
            return max(now+.0001, self.next_interactive if self.urgent_refresh else self.next_frame)
        return now+1.


class EncoderSnapshots:
    """Bounded, cumulative MCU snapshots; baseline/reconnect never replays UI.

    position is a wrapping count of valid quadrature quarter-transitions.
    No event queue grows on either side of the UART. Discontinuities and old
    sequence numbers are ignored; invalid transition count remains visible.
    """
    COUNTERS = ('presses', 'releases', 'shorts', 'longs')

    def __init__(self, steps_per_detent=4, reverse=False, validated=False):
        if steps_per_detent not in (1, 2, 4):
            raise ValueError('encoder_steps_per_detent must be 1, 2 or 4')
        self.steps_per_detent = steps_per_detent
        self.reverse = reverse
        self.validated = validated
        self.reset()

    def reset(self):
        self.previous = None
        self.residual = 0
        self.last_time = None
        self.discontinuities = 0
        self.ignored = 0

    def update(self, params, now):
        current = {k: int(params[k]) & 0xffffffff for k in
                   ('sequence', 'position', 'invalid') + self.COUNTERS}
        current['pressed'] = bool(params['pressed'])
        if self.validated:
            current['nav_position'] = int(params['nav_position']) & 0xffffffff
        old = self.previous
        if old is not None:
            seqdiff = (current['sequence'] - old['sequence']) & 0xffffffff
            if seqdiff == 0 or seqdiff >= 0x80000000:
                self.ignored += 1
                return None
        self.previous = current
        stale = self.last_time is None or now - self.last_time > 1.
        self.last_time = now
        if old is None or stale:
            self.residual = 0
            return None
        position_key = 'nav_position' if self.validated else 'position'
        delta = (current[position_key] - old[position_key]) & 0xffffffff
        if delta >= 0x80000000:
            delta -= 0x100000000
        events = {k: (current[k] - old[k]) & 0xffffffff for k in self.COUNTERS}
        if (abs(delta) > 128 or any(v > 8 for v in events.values())
                or (self.validated and delta % self.steps_per_detent)):
            self.discontinuities += 1
            self.residual = 0
            return None
        if current['invalid'] != old['invalid']:
            # Legacy snapshots cannot distinguish complete movement from
            # partial phases on either side of an ambiguous AB jump. ABI3
            # commits detents in the MCU and discards the partial there, so
            # its completed movement survives other invalid edges in a report.
            self.discontinuities += 1
            self.residual = 0
            if not self.validated:
                delta = 0
        self.residual += -delta if self.reverse else delta
        detents = abs(self.residual) // self.steps_per_detent
        if self.residual < 0:
            detents = -detents
        self.residual -= detents * self.steps_per_detent
        return dict(events, delta=detents, pressed=current['pressed'],
                    invalid=current['invalid'])
