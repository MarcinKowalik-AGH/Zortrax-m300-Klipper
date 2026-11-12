# SPDX-License-Identifier: GPL-3.0-or-later
"""One bounded native HomingMove capability, shared by M07 and Z refinement."""
import math


def boundary_z(value, bounds, error):
    lo, hi = bounds
    if type(value) not in (int, float) or not math.isfinite(value):
        raise error('non-finite native Z result')
    epsilon = 8. * math.ulp(max(1., abs(lo), abs(hi)))
    if lo-epsilon <= value < lo:
        return lo
    if hi < value <= hi+epsilon:
        return hi
    if not lo <= value <= hi:
        raise error('native Z result outside axis bounds')
    return value


class BoundedProbeToolhead:
    def __init__(self, toolhead, target, speed, check, drip, set_position,
                 normalize_z, error, *, halt_start=None):
        self.toolhead, self.start = toolhead, list(toolhead.get_position())
        self.halt_start = self.start if halt_start is None else halt_start
        self.target, self.speed = list(target), speed
        self.check, self.drip, self.set_native = check, drip, set_position
        self.normalize_z, self.error, self.used = normalize_z, error, False

    def __getattr__(self, name):
        return getattr(self.toolhead, name)

    def drip_move(self, position, speed, completion):
        self.check()
        if self.used or list(position) != self.target or speed != self.speed:
            raise self.error('native probe attempted an unexpected move')
        self.used = True
        return self.drip(list(position), speed, completion)

    def set_position(self, position, *args, **kwargs):
        self.check()
        p = list(position)
        if (args or kwargs or len(p) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                or any(abs(p[i]-self.halt_start[i]) > 1.e-6 for i in (0, 1, 3))
                or not min(self.halt_start[2], self.target[2])-1.e-6 <= p[2]
                       <= max(self.halt_start[2], self.target[2])+1.e-6):
            raise self.error('native probe returned an invalid position')
        p[2] = self.normalize_z(p[2])
        if self.halt_start is not self.start:
            p[0], p[1], p[3] = self.start[0], self.start[1], self.start[3]
        return self.set_native(p)
