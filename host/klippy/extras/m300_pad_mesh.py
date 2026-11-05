# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Klipper probing and compensation for the five Classic M300 pads."""
import json
import math
import re
import statistics

from .m300_calibration_state import POINTS
from .m300_native_service import require_idle_print

PATTERN = ((0, 0), (-1, -1), (1, -1), (1, 1), (-1, 1))
GRID_COUNT = 61
CLEARANCE = 5.
SEARCH_MARGIN = 1.


def pad_points(corner_width, margin, center_width=None):
    """Keep the legacy two-argument geometry, with a separate center width."""
    if center_width is None:
        center_width = corner_width
    if not (math.isfinite(margin) and all(
            math.isfinite(width) and .5 <= margin < width / 2 <= 50.
            for width in (corner_width, center_width))):
        raise ValueError('pad widths and edge_margin must leave a positive inset (width <= 100 mm)')
    points = []
    for index, (x, y) in enumerate(POINTS):
        span = (center_width if index == 2 else corner_width) / 2 - margin
        points.extend((x + dx * span, y + dy * span) for dx, dy in PATTERN)
    # The structured triangulation needs five separated, nested pad clusters.
    if not (points[8][0] < points[11][0] < points[13][0] < points[4][0]
            and points[8][1] < points[11][1] < points[13][1] < points[21][1]):
        raise ValueError('pad geometry must leave space between the five contact squares')
    return tuple(points)


def pad_triangles():
    """Tile the measured rectangle using all 25 vertices, without extrapolation."""
    triangles = []
    for start in range(0, 25, 5):
        for corner in range(1, 5):
            triangles.append((start, start + corner, start + corner % 4 + 1))
    # Four gaps along the outer edges, then four gaps around the center pad.
    for a, b, c, d in ((7, 1, 4, 8), (22, 16, 19, 23),
                       (9, 8, 22, 21), (4, 3, 17, 16),
                       (8, 4, 12, 11), (4, 16, 13, 12),
                       (16, 22, 14, 13), (22, 8, 11, 14)):
        triangles.extend(((a, b, c), (a, c, d)))
    return tuple(triangles)


def mesh_bounds(points):
    return (min(x for x, y in points), min(y for x, y in points),
            max(x for x, y in points), max(y for x, y in points))


def surface_grid(points, readings):
    """Resample a continuous piecewise-linear 25-point surface for native ZMesh."""
    if len(points) != 25 or len(readings) != 25 or not all(map(math.isfinite, readings)):
        raise ValueError('mesh requires 25 finite contact heights')
    planes = []
    reference = readings[10]
    for a, b, c in pad_triangles():
        ax, ay = points[a]
        bx, by = points[b]
        cx, cy = points[c]
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-9:
            raise ValueError('degenerate pad triangle')
        planes.append((cx, cy, (by - cy) / det, (cx - bx) / det,
                       (cy - ay) / det, (ax - cx) / det,
                       readings[a] - reference, readings[b] - reference,
                       readings[c] - reference))
    x0, y0, x1, y1 = mesh_bounds(points)
    grid = []
    for j in range(GRID_COUNT):
        y = y0 + (y1 - y0) * j / (GRID_COUNT - 1)
        row = []
        for i in range(GRID_COUNT):
            x = x0 + (x1 - x0) * i / (GRID_COUNT - 1)
            for cx, cy, au, av, bu, bv, za, zb, zc in planes:
                u = au * (x - cx) + av * (y - cy)
                v = bu * (x - cx) + bv * (y - cy)
                w = 1 - u - v
                if min(u, v, w) >= -1e-9:
                    # Remove roundoff at boundaries and keep a convex combination.
                    u, v, w = max(0., u), max(0., v), max(0., w)
                    row.append((u * za + v * zb + w * zc) / (u + v + w))
                    break
            else:
                raise ValueError('pad triangles do not cover the requested mesh')
        grid.append(row)
    return grid


class M300PadMesh:
    def __init__(self, config):
        from . import probe

        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        if not config.has_section('bed_mesh') or not config.has_section('probe'):
            raise config.error('M300 pad mesh requires [bed_mesh] and [probe]')
        pin = config.getsection('probe').get('pin').lstrip('^~!')
        if pin not in ('PC7', 'mcu:PC7'):
            raise config.error('M300 pad mesh requires the native PC7 contact probe')
        legacy_width = config.getfloat('pad_width', None)
        corner_width = config.getfloat('corner_pad_width',
                                       60. if legacy_width is None else legacy_width)
        center_width = config.getfloat('center_pad_width',
                                       50. if legacy_width is None else legacy_width)
        try:
            self.points = pad_points(corner_width, config.getfloat(
                'edge_margin', 5. if legacy_width is None else 1.), center_width)
        except ValueError as exc:
            raise config.error(str(exc))
        self.max_pad_spread = config.getfloat('max_pad_spread', None, above=0., maxval=.75)
        self.max_bed_span = config.getfloat('max_bed_span', .5, above=0., maxval=.75)
        self.bedmesh = self.printer.load_object(config, 'bed_mesh')
        self.state, self.busy = 'IDLE', False
        self.report = None

        owner = self

        class PadProbePoints(probe.ProbePointsHelper):
            def _move_next(self, probe_num):
                owner._check_clear()
                super()._move_next(probe_num)

        self.probe_points = PadProbePoints(config, self._capture, self.points)
        self.probe_points.update_probe_points(self.points, len(self.points))
        self.probe_points.use_xy_offsets(True)
        self.gcode.register_command('BED_MESH_CALIBRATE', None)
        self.gcode.register_command(
            'BED_MESH_CALIBRATE', self.cmd_calibrate,
            desc='Measure 25 contact points on the five Classic M300 pads')
        self.gcode.register_command(
            'ZORTRAX_PAD_MESH_STATUS', self.cmd_status,
            desc='Show the last M300 pad measurement and generated mesh profile')

    def _error(self, message):
        return self.printer.command_error('M300 pad mesh: ' + message)

    def _check_clear(self):
        if self.printer.is_shutdown():
            raise self._error('printer shut down during probing')
        self.toolhead.wait_moves()
        self.job.board.require_motion()
        self.job.board.require_heating()
        temperatures = self.job._temperatures(self.reactor.monotonic())
        for name, target in self.targets.items():
            measured, current_target = temperatures[name]
            if target != current_target or abs(measured - target) > 3.:
                raise self._error('temperature is no longer stable for ' + name)
        if self.endstop.query_endstop(self.toolhead.get_last_move_time()):
            raise self._error('PC7 must be open at clearance before XY travel')

    def _capture(self, results):
        self._check_clear()
        if len(results) != len(self.points):
            raise self._error('incomplete probe result')
        readings = []
        for (x, y), result in zip(self.points, results):
            if (not math.isclose(result.bed_x, x, abs_tol=.01)
                    or not math.isclose(result.bed_y, y, abs_tol=.01)
                    or not math.isfinite(result.bed_z)):
                raise self._error('probe result does not match the requested pad position')
            z = result.bed_z - self.shift
            if not -.75 <= z <= .75:
                raise self._error('contact lies outside the usable Z search range')
            readings.append(z)
        summaries = []
        for index, (x, y) in enumerate(POINTS):
            start = index * len(PATTERN)
            values = readings[start:start + len(PATTERN)]
            spread = max(values) - min(values)
            if self.max_pad_spread is not None and spread > self.max_pad_spread:
                raise self._error('pad %d is uneven or has inconsistent contact' % index)
            summaries.append(dict(x=x, y=y, z=statistics.median(values), spread=spread))
        if max(readings) - min(readings) > self.max_bed_span:
            raise self._error('bed span is too large; run Autocalibration first')
        self.samples = (readings, summaries)

    def _preflight(self):
        now = self.reactor.monotonic()
        require_idle_print(self.printer, now)
        self.job = self.printer.lookup_object('m300_job')
        if (not self.job.board.native_control or self.job.board.mcu.is_fileoutput()
                or self.job.service_busy() or self.job.get_status(now)['busy']):
            raise self._error('requires an idle native M300 with a physical MCU')
        self.toolhead = self.printer.lookup_object('toolhead')
        self.kin = self.toolhead.get_kinematics()
        limits = self.kin.get_status(now)
        if not set(limits['homed_axes']) >= set('xyz'):
            raise self._error('home XYZ before probing')
        low, high = limits['axis_minimum'], limits['axis_maximum']
        if any(not (low[0] <= x <= high[0] and low[1] <= y <= high[1])
               for x, y in self.points):
            raise self._error('pad geometry falls outside the configured XY travel')
        gcode_move = self.printer.lookup_object('gcode_move')
        if gcode_move.move_transform is not self.bedmesh or self.bedmesh.get_mesh() is not None:
            raise self._error('clear the active mesh before probing with BED_MESH_CLEAR')
        printer_probe = self.printer.lookup_object('probe')
        if tuple(printer_probe.get_offsets()) != (0., 0., 0.):
            raise self._error('requires zero offsets for the native nozzle contact probe')
        native_probe = printer_probe.mcu_probe
        self.endstop = native_probe.mcu_endstop
        if ([stepper.get_name() for stepper in self.endstop.get_steppers()] != ['stepper_z']
                or native_probe.homing_helper.z_min_position != low[2]):
            raise self._error('PC7 must own one native Z rail with its configured minimum')
        self.shift = low[2] + SEARCH_MARGIN
        self.horizontal_z = CLEARANCE + self.shift
        pos = self.toolhead.get_position()
        if not (low[2] <= self.horizontal_z <= high[2]
                and low[2] <= pos[2] + self.shift <= high[2]):
            raise self._error('move to a safe Z position before measuring')
        temps = self.job._temperatures(now)
        self.targets = {name: temps[name][1] for name in ('hotend', 'bed')}
        if self.targets['hotend'] < 180. or self.targets['bed'] <= 0.:
            raise self._error('heat the clean nozzle to at least 180 C and the bed to print temperature')
        self._check_clear()

    def _publish(self, profile, readings):
        from .bed_mesh import ZMesh

        x0, y0, x1, y1 = mesh_bounds(self.points)
        params = dict(min_x=x0, min_y=y0, max_x=x1, max_y=y1, algo='direct',
                      x_count=GRID_COUNT, y_count=GRID_COUNT,
                      mesh_x_pps=0, mesh_y_pps=0, tension=.2)
        mesh = ZMesh(params, profile)
        mesh.build_mesh(surface_grid(self.points, readings))
        mesh.set_zero_reference(*POINTS[2])
        try:
            self.bedmesh.set_mesh(mesh)
            self.bedmesh.save_profile(profile)
        finally:
            self.bedmesh.set_mesh(None)

    def cmd_calibrate(self, gcmd):
        profile = gcmd.get('PROFILE', 'm300_pads')
        if (self.busy or set(gcmd.get_command_parameters()) - {'PROFILE'}
                or not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}', profile)):
            raise self._error('only an idle pad run with an optional simple PROFILE name is supported')
        self._preflight()
        self.state, self.busy = 'PROBING', True
        self.samples = None
        shifted = completed = False
        try:
            pos = self.toolhead.get_position()
            pos[2] += self.shift
            self.toolhead.set_position(pos)
            shifted = True
            params = dict(HORIZONTAL_MOVE_Z=str(self.horizontal_z), PROBE_SPEED='0.5',
                          LIFT_SPEED='2', SAMPLES='3', SAMPLE_RETRACT_DIST='1',
                          SAMPLES_RESULT='median', SAMPLES_TOLERANCE='0.05',
                          SAMPLES_TOLERANCE_RETRIES='1')
            native_cmd = self.gcode.create_gcode_command('BED_MESH_CALIBRATE',
                                                       'BED_MESH_CALIBRATE', params)
            self.probe_points.start_probe(native_cmd)
            readings, pads = self.samples
            self.toolhead.wait_moves()
            pos = self.toolhead.get_position()
            pos[2] -= self.shift
            self.toolhead.set_position(pos)
            shifted = False
            self._publish(profile, readings)
            self.report = dict(profile=profile, pads=pads,
                               points=[[x, y, z] for (x, y), z in zip(self.points, readings)])
            completed = True
        finally:
            try:
                if shifted and not self.printer.is_shutdown():
                    self.toolhead.wait_moves()
                    pos = self.toolhead.get_position()
                    pos[2] -= self.shift
                    self.kin.clear_homing_state('z')
                    self.toolhead.set_position(pos)
            finally:
                self.busy = False
                self.state = 'COMPLETE' if completed else 'FAILED'
        gcmd.respond_info('Measured 25 pad positions. Load %s for printing; use SAVE_CONFIG to keep it.'
                          % profile)

    def get_status(self, eventtime):
        return dict(state=self.state, busy=self.busy, result=self.report)

    def cmd_status(self, gcmd):
        status = self.get_status(self.reactor.monotonic())
        gcmd.respond_info('M300_PAD_MESH ' + json.dumps(dict(status, probe_points=self.points)))


def load_config(config):
    return M300PadMesh(config)
