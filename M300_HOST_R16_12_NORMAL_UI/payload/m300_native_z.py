# SPDX-License-Identifier: GPL-3.0-or-later
"""Five successive PC7 contact/release reference updates using native Klipper.

OEM 0x0800ab90/0x0800ac10 supplies the iteration and last-reference policy.
Unlike its unbounded release loop, every native search/release has a finite
endpoint. A full 1 mm retreat verifies stable opening; no mean is substituted.
"""
import math

from .m300_native_probe import BoundedProbeToolhead, boundary_z


class M300ZRefinement:
    contacts = 5
    search = 5.
    release = 1.
    margin = 1.
    speed = .5
    timeout = 45.

    def __init__(self, owner, probe):
        self.owner, self.printer = owner, owner.printer
        self.toolhead, self.probe = owner.toolhead, probe
        wrapper = getattr(probe, 'mcu_probe', None)
        self.endstop = getattr(wrapper, 'mcu_endstop', None)
        if self.endstop is None:
            raise owner.config.error('M300 precision Z requires the existing PC7 endstop')
        self.drip, self.set_native = self.toolhead.drip_move, self.toolhead.set_position
        self.references = []

    def error(self, message):
        return self.printer.command_error('M300 precision Z: '+message)

    def check_temperature(self):
        measured, target = self.owner.hotend.get_temp(self.owner.reactor.monotonic())
        expected = self.owner._z_target
        if target != expected:
            raise self.error('nozzle target changed from %.1f C to %.1f C during contact reference'
                             % (expected, target))
        if not math.isfinite(measured) or measured == 0.:
            raise self.error('no valid nozzle temperature during contact reference')
        minimum = (self.owner.z_home_hotend_target
                   - self.owner.z_home_temperature_tolerance)
        if measured < minimum:
            raise self.error('nozzle temperature %.2f C below contact minimum %.2f C (target %.1f C)'
                             % (measured, minimum, expected))

    def check(self):
        self.owner._check(self.token)
        self.owner.board.require_motion()
        self.owner.board.require_heating()
        self.check_temperature()
        if self.owner.reactor.monotonic() > self.deadline:
            raise self.error('bounded contact/release deadline exceeded')

    def normalized(self, z):
        return boundary_z(z,self.bounds,self.error)

    def query(self):
        self.check()
        result = self.endstop.query_endstop(self.toolhead.get_last_move_time())
        self.check()
        return bool(result)

    def move(self, z, speed):
        self.check()
        z = self.normalized(z)
        self.toolhead.manual_move([None,None,z],speed)
        self.toolhead.wait_moves()
        self.check()

    def transition(self, z, triggered):
        from . import homing
        self.check()
        target = list(self.toolhead.get_position())
        target[2] = self.normalized(z)
        proxy = BoundedProbeToolhead(self.toolhead,target,self.speed,self.check,
            self.drip,self.set_native,self.normalized,self.error)
        move = homing.HomingMove(self.printer,[(self.endstop,'m300_z_reference')],toolhead=proxy)
        result = move.homing_move(target,self.speed,probe_pos=True,
                                  triggered=triggered,check_triggered=True)
        self.check()
        if move.check_no_movement() is not None:
            raise self.error('PC7 transition occurred without movement')
        return self.normalized(result[2])

    def run(self, token):
        self.token = token
        steppers=self.endstop.get_steppers()
        if len(steppers)!=1 or steppers[0].get_name()!='stepper_z':
            raise self.error('PC7 must own exactly one native Z stepper')
        self.bounds = self.toolhead.get_kinematics().rails[2].get_range()
        lo,hi = self.bounds
        self.references = []
        self.deadline = self.owner.reactor.monotonic()+self.timeout
        origin = self.probe.get_offsets()[2]
        # The native coarse home is genuine. This temporary translated frame
        # permits a bounded search below its contact without changing limits.
        self.move(origin+4.,self.owner.lift_speed)
        if self.query():
            raise self.error('INITIAL_ACTIVE: PC7 did not release after coarse home')
        position = list(self.toolhead.get_position())
        position[2] = self.normalized(position[2]+self.margin)
        self.set_native(position)
        self.printer.send_event('toolhead:manual_move')
        scale = self.owner.board.hardware.get_status()['effective_z_steps_per_mm']
        if scale not in (400,800):
            raise self.error('factory Z400/Z800 scale is required')
        last = None
        for index in range(self.contacts):
            self.deadline = self.owner.reactor.monotonic()+self.timeout
            if self.query():
                raise self.error('INITIAL_ACTIVE: contact must be open before approach')
            start = self.toolhead.get_position()[2]
            target = max(lo,start-self.search)
            if target >= start:
                raise self.error('no bounded approach remains')
            contact = self.transition(target,True)
            if not self.query():
                raise self.error('PC7 contact was not stable after approach')
            release_target = contact+self.release
            if release_target > hi:
                raise self.error('release endpoint outside native Z range')
            last = self.transition(release_target,False)
            if last <= contact:
                raise self.error('NO_RELEASE: invalid PC7 release edge')
            # The source adds 100 counts after each release. Retain at least
            # that distance and complete a full stable 1 mm opening as in M07.
            self.move(last+max(100./scale,self.release),self.speed)
            self.toolhead.dwell(1.)
            self.toolhead.wait_moves()
            self.check()
            if self.query():
                raise self.error('NO_RELEASE: PC7 reclosed after full retreat')
            self.references.append(dict(iteration=index+1,
                contact_mm=contact-self.margin,release_mm=last-self.margin))
        # Use the fifth release reference. Keep physical clearance; do not
        # return blindly into the electrical edge just to assign an origin.
        position = list(self.toolhead.get_position())
        position[2] = self.normalized(position[2]-last+origin)
        self.check()
        self.set_native(position)
        self.printer.send_event('toolhead:manual_move')
        return dict(method='FIVE_SUCCESSIVE_RELEASE_REFERENCES',contacts=len(self.references),
                    averaging=False,references=list(self.references),
                    final_reference_mm=last-self.margin,stable_release_mm=self.release)
