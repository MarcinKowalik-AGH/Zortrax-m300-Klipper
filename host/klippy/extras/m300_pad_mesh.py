# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Klipper probing and compensation for the five Classic M300 pads."""
import json
import math
import os
import re
import statistics

from .m300_calibration_state import POINTS
from .m300_native_service import require_idle_print

PATTERN = ((0, 0), (-1, -1), (1, -1), (1, 1), (-1, 1))
GRID_COUNT = 61
CLEARANCE = 5.
SEARCH_MARGIN = 1.
PAD_NAMES = ('front_right', 'front_left', 'center', 'rear_right', 'rear_left')
BOUNDS_FIELDS = tuple(name + '_bounds' for name in PAD_NAMES)
PAD_CENTERS = ((290., 30.), (30., 30.), (160., 160.), (290., 290.), (30., 290.))
TEMPERATURE_SETTLE = 3.
GEOMETRY_DEFAULTS = dict(corner_pad_width=50., center_pad_width=50., edge_margin=5.)
GEOMETRY_DEFAULTS.update((name + '_' + axis, value)
                         for name, point in zip(PAD_NAMES, PAD_CENTERS)
                         for axis, value in zip('xy', point))


def preparation_targets(temperatures, overrides, minimum_hotend=180., default_bed=60., default_hotend=None):
    """180 C is a floor; retain a hotter working target or an already-hot idle nozzle."""
    measured, current = temperatures['hotend']
    bed_current = temperatures['bed'][1]
    requested = overrides.get('HOTEND_TEMP', minimum_hotend if default_hotend is None else default_hotend)
    bed = overrides.get('BED_TEMP', bed_current if bed_current > 0. else default_bed)
    values = (measured, current, bed_current, requested, bed, minimum_hotend, default_bed)
    if (not all(math.isfinite(value) for value in values) or requested < 180. or bed <= 0.):
        raise ValueError('HOTEND_TEMP must be at least 180 C and BED_TEMP must be positive and finite')
    target = max(minimum_hotend, requested, current)
    if current < minimum_hotend or measured > current + 3.:
        target = max(target, measured)
    return dict(hotend=target, bed=bed)


def parse_pad_bounds(value, name):
    if value is None or isinstance(value,str) and value.strip().upper() == 'AUTO':
        return None
    try:
        values = tuple(float(v) for v in (value.split(',') if isinstance(value,str) else value))
    except (TypeError,ValueError):
        raise ValueError('%s must contain X_MIN,Y_MIN,X_MAX,Y_MAX or AUTO' % name)
    if len(values) != 4 or not all(map(math.isfinite,values)):
        raise ValueError('%s must contain four finite coordinates' % name)
    return values


def pad_points(corner_width, margin, center_width=None, centers=POINTS, bounds=None):
    """Keep the legacy two-argument geometry, with a separate center width."""
    if center_width is None:
        center_width = corner_width
    if not math.isfinite(margin) or margin < 0.:
        raise ValueError('edge_margin must be finite and >= 0 mm; zero probes the metal edge')
    if not all(math.isfinite(width) and 0. < width <= 100.
               for width in (corner_width, center_width)):
        raise ValueError('pad widths must be finite and in (0, 100] mm')
    if margin >= min(corner_width, center_width) / 2:
        raise ValueError('edge_margin %g mm must be less than half of both pad widths '
                         '(corner %g mm, center %g mm)' % (margin, corner_width, center_width))
    if len(centers) != 5 or not all(math.isfinite(v) for point in centers for v in point):
        raise ValueError('pad centers must contain five finite XY positions')
    points = []
    for index, (x, y) in enumerate(centers):
        rectangle = (bounds or {}).get(index)
        if rectangle is not None:
            x0,y0,x1,y1 = rectangle
            if not (x0 < x < x1 and y0 < y < y1 and x1-x0 <= 100. and y1-y0 <= 100.):
                raise ValueError('%s bounds must enclose its configured center and span at most 100 mm per axis'
                                 % PAD_NAMES[index])
            # Explicit contact bounds are the requested corners. Do not
            # apply the legacy square's width/inset a second time.
            points.extend(((x,y),(x0,y0),(x1,y0),(x1,y1),(x0,y1)))
            continue
        span = (center_width if index == 2 else corner_width) / 2 - margin
        points.extend((x + dx * span, y + dy * span) for dx, dy in PATTERN)
    validate_layout(points)
    return tuple(points)


def validate_layout(points):
    # The structured triangulation needs five separated, nested pad clusters.
    if not (max(points[8][0], points[22][0]) < points[11][0]
            < points[13][0] < min(points[4][0], points[16][0])
            and max(points[8][1], points[4][1]) < points[11][1]
            < points[13][1] < min(points[21][1], points[16][1])):
        raise ValueError('pad geometry must leave space between the five contact squares')
    for a, b, c in pad_triangles():
        ax, ay = points[a]
        bx, by = points[b]
        cx, cy = points[c]
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 1e-9:
            raise ValueError('pad corrections must preserve the contact-square layout')


def fit_pad_points(points, minimum, maximum, margin=1.):
    """Clip only pad corners to reachable metal; never relocate a pad center."""
    if (not math.isfinite(margin) or not 0. <= margin <= 5.
            or not all(math.isfinite(v) for bounds in (minimum, maximum) for v in bounds[:2])):
        raise ValueError('TRAVEL_MARGIN must be 0..5 mm with finite XY travel')
    fitted = []
    for start, name in zip(range(0,25,5), PAD_NAMES):
        cx, cy = points[start]
        x0, y0 = points[start+1]
        x1, y1 = points[start+3]
        x0, y0 = max(x0, minimum[0]+margin), max(y0, minimum[1]+margin)
        x1, y1 = min(x1, maximum[0]-margin), min(y1, maximum[1]-margin)
        if not (x0 < cx < x1 and y0 < cy < y1):
            raise ValueError('%s pad center X%g Y%g has no reachable four-corner area; '
                             'correct its center or verify XY travel' % (name,cx,cy))
        fitted.extend(((cx,cy),(x0,y0),(x1,y0),(x1,y1),(x0,y1)))
    validate_layout(fitted)
    return tuple(fitted)


def geometry_points(geometry):
    centers = tuple(tuple(geometry[name + '_' + axis] for axis in 'xy')
                    for name in PAD_NAMES)
    bounds = {index:parse_pad_bounds(geometry.get(key),key)
              for index,key in enumerate(BOUNDS_FIELDS)}
    return pad_points(geometry['corner_pad_width'], geometry['edge_margin'],
                      geometry['center_pad_width'], centers,bounds)


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
    # Stay inside both pads on each side when their individual centers differ.
    return (max(points[6][0], points[21][0]), max(points[1][1], points[6][1]),
            min(points[2][0], points[17][0]), min(points[19][1], points[24][1]))


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
        defaults = dict(GEOMETRY_DEFAULTS)
        if legacy_width is not None:
            defaults.update(corner_pad_width=legacy_width, center_pad_width=legacy_width,
                            edge_margin=1.)
            defaults.update((name + '_' + axis, value)
                            for name, point in zip(PAD_NAMES, POINTS)
                            for axis, value in zip('xy', point))
        self.geometry = {key: config.getfloat(key, value) for key, value in defaults.items()}
        for key in BOUNDS_FIELDS:
            try:
                rectangle = parse_pad_bounds(config.get(key,None),key)
            except ValueError as exc:
                raise config.error(str(exc))
            if rectangle is not None:self.geometry[key] = rectangle
        self.fit_travel = config.getboolean('fit_travel', True)
        self.travel_margin = config.getfloat('travel_margin', 1., minval=0., maxval=5.)
        if not math.isfinite(self.travel_margin):
            raise config.error('travel_margin must be finite')
        try:
            self.points = geometry_points(self.geometry)
        except ValueError as exc:
            raise config.error(str(exc))
        self.nominal_points = self.points
        self.max_pad_spread = config.getfloat('max_pad_spread', None, above=0., maxval=.75)
        self.max_bed_span = config.getfloat('max_bed_span', .8, above=0., maxval=1.5)
        if (not math.isfinite(self.max_bed_span)
                or self.max_pad_spread is not None and not math.isfinite(self.max_pad_spread)):
            raise config.error('pad spread and bed span limits must be finite')
        self.hotend_temperature = config.getfloat('hotend_temperature', 260., minval=180.)
        self.bed_temperature = config.getfloat('bed_temperature', 60., above=0.)
        self.heat_timeout = config.getfloat('heat_timeout', 1800., minval=60., maxval=3600.)
        if not all(math.isfinite(value) for value in (
                self.hotend_temperature, self.bed_temperature, self.heat_timeout)):
            raise config.error('pad preparation temperatures and timeout must be finite')
        self.bedmesh = self.printer.load_object(config, 'bed_mesh')
        self.state, self.busy = 'IDLE', False
        self.phase, self.cancelled = 'IDLE', False
        self.report = None
        self.run_id = None
        self.points_measured = 0
        self.measurements = []
        self.rejected_contact = None
        self.last_error = ''
        self.last_attempt = None
        for event in ('klippy:shutdown', 'klippy:disconnect', 'gcode:request_restart'):
            self.printer.register_event_handler(event, lambda *args,event=event:self._stop(event))

        owner = self

        class PadProbePoints(probe.ProbePointsHelper):
            def _raise_tool(self, is_first=False):
                if not is_first and owner.busy and owner.phase == 'PROBING':
                    # Read the pinned native session's completed medians.
                    # Never drain its result queue or count individual taps
                    # (including samples discarded by native retry logic).
                    session = self.printer.lookup_object('probe').probe_session
                    owner._update_measurements(session.results)
                super()._raise_tool(is_first)

            def _move_next(self, probe_num):
                owner.points_measured = probe_num
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

    def _notify_view(self):
        notify = getattr(self.printer, 'send_event', None)
        if notify is not None:
            notify('m300:pad_mesh_view_changed')

    def _stop(self, reason):
        if self.busy:
            self.cancelled = True
            self.last_error = reason
            self.state, self.phase, self.busy = 'FAILED', 'FAILED', False
            self._turn_off()
            self._notify_view()

    def _turn_off(self):
        job = getattr(self, 'job', None)
        for name in ('hotend', 'bed'):
            heater = getattr(job, name, None)
            if heater is not None:
                heater.set_temp(0.)

    def _check_session(self, token):
        if (self.printer.is_shutdown() or self.cancelled or not self.busy
                or self.state != 'PROBING' or self.run_id != token):
            raise self._error('measurement session ended during ' + self.phase)
        self.job.board.require_motion()
        self.job.board.require_heating()

    def _restore_targets(self, token):
        previous = getattr(self,'previous_targets',None)
        if previous is None:return
        for name,target in previous.items():
            self._check_session(token)
            heater = getattr(self.job,name)
            # An explicit off/change after probing must not be overwritten.
            if heater.get_temp(self.reactor.monotonic())[1] == self.targets[name]:
                heater.set_temp(target)

    def _check_clear(self):
        if self.printer.is_shutdown():
            raise self._error('printer shut down during probing')
        self.toolhead.wait_moves()
        self.job.board.require_motion()
        self.job.board.require_heating()
        self._check_temperatures()
        if self.endstop.query_endstop(self.toolhead.get_last_move_time()):
            raise self._error('PC7 must be open at clearance before XY travel')

    def _check_temperatures(self):
        temperatures = self.job._temperatures(self.reactor.monotonic())
        for name, target in self.targets.items():
            measured, current_target = temperatures[name]
            if (not all(math.isfinite(value) for value in (measured, current_target, target))
                    or target != current_target or abs(measured - target) > 3.):
                raise self._error('temperature is no longer stable for ' + name)

    def _update_measurements(self, results):
        if len(results) > len(self.points):
            raise self._error('too many probe results')
        measured = []
        low, high = getattr(self, 'probe_bounds', (self.shift - SEARCH_MARGIN,
                                                  self.shift + CLEARANCE))
        minimum, maximum = low - self.shift, high - self.shift
        for index, ((x, y), result) in enumerate(zip(self.points, results)):
            if (not math.isclose(result.bed_x, x, abs_tol=.01)
                    or not math.isclose(result.bed_y, y, abs_tol=.01)
                    or not math.isfinite(result.bed_z)):
                raise self._error('probe result does not match the requested pad position')
            z = result.bed_z - self.shift
            # A contact height is relative to the homing datum. Its absolute
            # value is not the bed's max-minus-min span. Validate the same
            # bounded native probe envelope, without extending any move.
            if not minimum - 1e-9 <= z <= maximum + 1e-9:
                self.rejected_contact = dict(run_id=getattr(self,'run_id',None),
                    point=index+1, pad=PAD_NAMES[index//5], x=x, y=y, z=z,
                    minimum_z=minimum, maximum_z=maximum)
                raise self._error('contact X%.3f Y%.3f Z%.4f mm is outside native Z '
                                  'search window [%.4f, %.4f] mm' % (x,y,z,minimum,maximum))
            measured.append([x, y, z])
        self.measurements = measured
        self.points_measured = len(measured)

    def _capture(self, results):
        self._check_clear()
        if len(results) != len(self.points):
            raise self._error('incomplete probe result')
        self._update_measurements(results)
        readings = [point[2] for point in self.measurements]
        summaries = []
        for index in range(5):
            start = index * len(PATTERN)
            x, y = self.points[start]
            values = readings[start:start + len(PATTERN)]
            spread = max(values) - min(values)
            summaries.append(dict(x=x, y=y, z=statistics.median(values), spread=spread))
        span = max(readings) - min(readings)
        self.last_attempt = dict(run_id=getattr(self,'run_id',None), accepted=False,
            points=[[x,y,z] for (x,y),z in zip(self.points,readings)], pads=summaries,
            span_mm=span, min_mm=min(readings), max_mm=max(readings),
            limit_mm=self.max_bed_span)
        for index,pad in enumerate(summaries):
            if self.max_pad_spread is not None and pad['spread'] > self.max_pad_spread:
                raise self._error('pad %d is uneven or has inconsistent contact' % index)
        if span > self.max_bed_span and not math.isclose(span, self.max_bed_span, rel_tol=0., abs_tol=1e-9):
            raise self._error('bed span is too large: %.4f mm exceeds max_bed_span %.4f mm; '
                              'run Autocalibration first. No new mesh profile was created' %
                              (span,self.max_bed_span))
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
        low, high = limits['axis_minimum'], limits['axis_maximum']
        travel = self._geometry_travel(limits)
        if not travel['fits']:
            raise self._error('pad geometry falls outside the configured XY travel: '
                'requested X%g..%g Y%g..%g; configured X%g..%g Y%g..%g. '
                'Use BED_MESH PREVIEW=1 for a fitting inset.' % (
                    *travel['required_x'], *travel['required_y'],
                    *travel['configured_x'], *travel['configured_y']))
        gcode_move = self.printer.lookup_object('gcode_move')
        if gcode_move.move_transform is not self.bedmesh:
            raise self._error('requires the native Bed Mesh motion transform')
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
        self.probe_bounds = (native_probe.homing_helper.z_min_position, self.horizontal_z)
        if not low[2] <= self.horizontal_z <= high[2]:
            raise self._error('configured Z travel cannot provide probe clearance')
        self.motion = self.printer.lookup_object('m300_motion')
        self.job.board.require_motion()
        self.job.board.require_heating()
        temperatures = self.job._temperatures(now)
        self.previous_targets = {name:values[1] for name,values in temperatures.items()}
        try:
            self.targets = preparation_targets(temperatures, getattr(self,'temperature_params',{}),
                max(180.,self.motion.z_home_hotend_target),
                getattr(self,'bed_temperature',60.),getattr(self,'hotend_temperature',260.))
        except ValueError as exc:
            raise self._error(str(exc))
        for name in ('hotend','bed'):
            heater = getattr(self.job,name)
            if not heater.min_temp <= self.targets[name] <= heater.max_temp:
                raise self._error('requested temperature outside native heater limits: ' + name)
        # A reference made before a significant temperature change must be
        # renewed after the bed and nozzle settle, even if XYZ still says homed.
        self.renew_z = any(abs(values[0]-self.targets[name]) > 3.
                           for name,values in temperatures.items())

    def _wait_temperatures(self, token):
        now = self.reactor.monotonic()
        deadline = now + getattr(self,'heat_timeout',1800.)
        stable_since = None
        while True:
            self._check_session(token)
            temperatures = self.job._temperatures(now)
            stable = True
            for name,target in self.targets.items():
                measured,current = temperatures[name]
                if not all(math.isfinite(value) for value in (measured,current)) or current != target:
                    raise self._error('temperature target changed during preparation: ' + name)
                stable = stable and abs(measured-target) <= 3.
            if stable:
                if stable_since is None:stable_since=now
                if now-stable_since >= TEMPERATURE_SETTLE:return
            else:
                stable_since = None
            if now >= deadline:
                raise self._error('temperature preparation timed out before probing')
            now = self.reactor.pause(min(now+.5,deadline))

    def _prepare(self, token):
        self.phase = 'CLEARANCE'
        self._check_session(token)
        self.bedmesh.set_mesh(None)
        # Match native Heater ownership. Flush once, then revalidate before
        # synchronous targets so a shutdown during lookahead cannot reheat.
        self.toolhead.register_lookahead_callback(lambda print_time:None)
        self._check_session(token)
        self.motion.ensure_xy_clearance(lambda:self._check_session(token))
        self._check_session(token)
        self.phase = 'HEATING'
        self.job.hotend.set_temp(self.targets['hotend'])
        self.job.bed.set_temp(self.targets['bed'])
        self._wait_temperatures(token)
        self.phase = 'HOMING'
        limits = self.kin.get_status(self.reactor.monotonic())
        missing = ''.join(axis for axis in 'xyz'
                          if axis not in limits['homed_axes'] or axis == 'z' and self.renew_z)
        if missing:
            axes = missing if missing in ('x','y','xy','z') else 'xyz'
            if axes in ('x','y','xy'):
                self.toolhead.wait_moves()
                if self.endstop.query_endstop(self.toolhead.get_last_move_time()):
                    axes = 'xyz'  # Native XYZ releases a closed PC7 before XY travel.
            self.gcode.respond_info('Pad mesh: homing %s before probing' % axes.upper())
            self.motion.home(axes=axes)
            self._check_session(token)
            self.phase = 'STABILIZING'
            self._wait_temperatures(token)
        limits = self.kin.get_status(self.reactor.monotonic())
        if not set(limits['homed_axes']) >= set('xyz'):
            raise self._error('native homing did not establish XYZ; probing was not started')
        self.motion.ensure_xy_clearance(lambda:self._check_session(token))
        low,high = limits['axis_minimum'],limits['axis_maximum']
        pos = self.toolhead.get_position()
        if not low[2] <= pos[2]+self.shift <= high[2]:
            raise self._error('move to a safe Z position before measuring')
        self._check_clear()
        self.phase = 'PROBING'

    def _publish(self, profile, readings):
        from .bed_mesh import ZMesh

        x0, y0, x1, y1 = mesh_bounds(self.points)
        params = dict(min_x=x0, min_y=y0, max_x=x1, max_y=y1, algo='direct',
                      x_count=GRID_COUNT, y_count=GRID_COUNT,
                      mesh_x_pps=0, mesh_y_pps=0, tension=.2)
        mesh = ZMesh(params, profile)
        mesh.build_mesh(surface_grid(self.points, readings))
        # Correcting a pad center must not move the native homing Z datum.
        mesh.set_zero_reference(*self.printer.lookup_object('m300_motion').home_xy)
        try:
            self.bedmesh.set_mesh(mesh)
            self.bedmesh.save_profile(profile)
        finally:
            self.bedmesh.set_mesh(None)

    def cmd_calibrate(self, gcmd):
        profile = gcmd.get('PROFILE', 'm300_pads')
        allowed = {key.upper() for key in (*GEOMETRY_DEFAULTS,*BOUNDS_FIELDS)} | {
            'PROFILE', 'PREVIEW', 'FIT_TRAVEL', 'TRAVEL_MARGIN', 'HOTEND_TEMP', 'BED_TEMP'}
        if (self.busy or set(gcmd.get_command_parameters()) - allowed
                or not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}', profile)):
            raise self._error('requires an idle pad run with a simple PROFILE and supported pad parameters')
        preview = gcmd.get_int('PREVIEW', 0, minval=0, maxval=1)
        fit = bool(gcmd.get_int('FIT_TRAVEL', int(getattr(self,'fit_travel',True)), minval=0, maxval=1))
        travel_margin = gcmd.get_float('TRAVEL_MARGIN', getattr(self,'travel_margin',1.))
        if not math.isfinite(travel_margin) or not 0. <= travel_margin <= 5.:
            raise self._error('TRAVEL_MARGIN must be 0..5 mm')
        geometry = {key: gcmd.get_float(key.upper(), self.geometry.get(key,value))
                    for key,value in GEOMETRY_DEFAULTS.items()}
        try:
            for key in BOUNDS_FIELDS:
                rectangle = parse_pad_bounds(gcmd.get(key.upper(),self.geometry.get(key)),key)
                if rectangle is not None:geometry[key] = rectangle
            nominal = points = geometry_points(geometry)
            toolhead = self.printer.lookup_object('toolhead', None)
            if fit and toolhead is not None:
                limits = toolhead.get_kinematics().get_status(self.reactor.monotonic())
                points = fit_pad_points(points, limits['axis_minimum'], limits['axis_maximum'], travel_margin)
        except ValueError as exc:
            raise self._error(str(exc))
        self.probe_points.update_probe_points(points, len(points))
        self.geometry, self.points = geometry, points
        self.nominal_points, self.fit_travel, self.travel_margin = nominal, fit, travel_margin
        if preview:
            self.cmd_status(gcmd)
            return
        self.temperature_params = {key:gcmd.get_float(key) for key in ('HOTEND_TEMP','BED_TEMP')
                                   if key in gcmd.get_command_parameters()}
        self._preflight()
        adjusted = sum(a != b for a,b in zip(nominal,points))
        if adjusted:
            gcmd.respond_info('Pad travel fit: adjusted %d corner points inside XY limits; '
                              'all five centers and pad sizes are retained. '
                              'Use PREVIEW=1 to review the contact plan.' % adjusted)
        self.state, self.busy = 'PROBING', True
        self.run_points = self.points
        self.phase, self.cancelled = 'PREPARING', False
        self.run_id = os.urandom(12).hex()
        token = self.run_id
        self.points_measured, self.last_error, self.last_attempt = 0, '', None
        self.measurements = []
        self.rejected_contact = None
        self.samples = None
        self._notify_view()
        shifted = completed = False
        try:
            self._prepare(token)
            self._check_session(token)
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
            self._check_session(token)
            readings, pads = self.samples
            self.toolhead.wait_moves()
            self._check_session(token)
            pos = self.toolhead.get_position()
            pos[2] -= self.shift
            self.toolhead.set_position(pos)
            shifted = False
            self._publish(profile, readings)
            self._check_session(token)
            self._restore_targets(token)
            self.report = dict(profile=profile, pads=pads, run_id=self.run_id,
                               points=[[x, y, z] for (x, y), z in zip(self.points, readings)])
            if self.last_attempt is not None:
                self.last_attempt = dict(self.last_attempt, accepted=True)
            completed = True
        except Exception as exc:
            self.last_error = str(exc)
            from .m300_error_codes import report
            report(self.printer, exc, source='m300_pad_mesh',
                   fatal=self.printer.is_shutdown())
            self._turn_off()
            raise
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
                self.phase = self.state
                self._notify_view()
        gcmd.respond_info('Measured 25 pad positions. Load %s for printing; use SAVE_CONFIG to keep it.'
                          % profile)

    def _geometry_travel(self, limits):
        low, high = limits['axis_minimum'], limits['axis_maximum']
        xs, ys = zip(*self.points)
        conflicts = [dict(point=index, pad=PAD_NAMES[index // 5], x=x, y=y)
                     for index, (x, y) in enumerate(self.points)
                     if not (low[0] <= x <= high[0] and low[1] <= y <= high[1])]
        result = dict(fits=not conflicts, required_x=[min(xs), max(xs)],
                      required_y=[min(ys), max(ys)], configured_x=[low[0], high[0]],
                      configured_y=[low[1], high[1]], outside_points=conflicts)
        if conflicts:
            # Only suggest an inset inside the reported metal and existing
            # travel. Never silently change the geometry or motor limits.
            margin = self.geometry['edge_margin']
            for index, name in enumerate(PAD_NAMES):
                width = self.geometry['center_pad_width' if index == 2 else 'corner_pad_width']
                for axis, letter in enumerate('xy'):
                    center = self.geometry[name + '_' + letter]
                    margin = max(margin, width / 2 - (center - low[axis]),
                                 width / 2 - (high[axis] - center))
            margin = math.ceil(margin + 1.)  # Leave 1 mm inside travel too.
            try:
                points = geometry_points(dict(self.geometry, edge_margin=margin))
            except ValueError:
                points = ()
            if points and all(low[0] <= x <= high[0] and low[1] <= y <= high[1] for x, y in points):
                result['suggested_edge_margin'] = margin
        return result

    def get_status(self, eventtime):
        toolhead = self.printer.lookup_object('toolhead', None)
        limits = toolhead.get_kinematics().get_status(eventtime) if toolhead is not None else None
        nominal = getattr(self,'nominal_points',self.points)
        changes = [dict(point=index,pad=PAD_NAMES[index//5],requested=list(a),actual=list(b))
                   for index,(a,b) in enumerate(zip(nominal,self.points)) if a != b]
        regions = [dict(name=name,center=list(nominal[index*5]),
                        bounds=[*nominal[index*5+1],*nominal[index*5+3]],
                        explicit=BOUNDS_FIELDS[index] in self.geometry)
                   for index,name in enumerate(PAD_NAMES)]
        return dict(revision='0.13.16.26-SAVED-MESH-VIEW', state=self.state, busy=self.busy, result=self.report,
                    operation='BED_MESH', session_token=getattr(self,'run_id',None) or 0,
                    phase=getattr(self,'phase','IDLE'), targets=getattr(self,'targets',None),
                    run_id=getattr(self,'run_id',None), points_measured=getattr(self,'points_measured',0),
                    plan_matches_run=getattr(self,'run_points',None) == self.points,
                    measurements=[list(point) for point in getattr(self,'measurements',())],
                    rejected_contact=getattr(self,'rejected_contact',None),
                    native_contact_window=[-SEARCH_MARGIN,CLEARANCE],
                    total_points=len(self.points), last_error=getattr(self,'last_error',''),
                    last_attempt=getattr(self,'last_attempt',None), max_bed_span=getattr(self,'max_bed_span',.8),
                    geometry=dict(self.geometry), mesh_bounds=mesh_bounds(self.points),
                    contact_regions=regions, probe_points=[list(point) for point in self.points],
                    fit_travel=getattr(self,'fit_travel',True),
                    travel_margin=getattr(self,'travel_margin',1.), adjusted_points=changes,
                    travel=self._geometry_travel(limits) if limits else None)

    def cmd_status(self, gcmd):
        status = self.get_status(self.reactor.monotonic())
        gcmd.respond_info('M300_PAD_MESH ' + json.dumps(dict(status, probe_points=self.points)))
        travel = status['travel']
        if travel is not None:
            gcmd.respond_info('Pad points X%g..%g Y%g..%g; configured travel X%g..%g Y%g..%g: %s' % (
                *travel['required_x'], *travel['required_y'],
                *travel['configured_x'], *travel['configured_y'],
                'fits' if travel['fits'] else 'OUTSIDE TRAVEL'))
            if status['adjusted_points']:
                gcmd.respond_info('Travel fit adjusted %d corners inside the pads; '
                                  'pad centers are unchanged. FIT_TRAVEL=0 requests exact geometry.' %
                                  len(status['adjusted_points']))
            if 'suggested_edge_margin' in travel:
                gcmd.respond_info('Keep the configured travel: preview a smaller contact area with '
                    'BED_MESH_CALIBRATE EDGE_MARGIN=%g PREVIEW=1. '
                    'This reduces corner coverage; motor limits are unchanged.' % travel['suggested_edge_margin'])


def load_config(config):
    return M300PadMesh(config)
