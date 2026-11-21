# Marcin Kowalik <mkowalik@agh.edu.pl>
# Regression checks for post-calibration clearance and parking.
from types import SimpleNamespace as NS
import unittest
from payload.m300_native_service import park_calibration

class CalibrationParkTests(unittest.TestCase):
    def fixture(self, closed=False, xy=(300.,305.)):
        position=[150.,158.,1.,17.];moves=[]
        kin=NS(get_status=lambda now:dict(homed_axes='xyz'))
        head=NS(get_position=lambda:position[:],wait_moves=lambda:None,
                get_kinematics=lambda:kin,get_last_move_time=lambda:0.)
        owner=NS(toolhead=head,reactor=NS(monotonic=lambda:0.),_error=ValueError,
                 printer=NS(lookup_object=lambda name,default=None:NS(park_xy=xy)))
        def move(pos,speed):moves.append((pos[:],speed));position[:]=pos
        return owner,move,NS(query_endstop=lambda when:closed),position,moves
    def test_lifts_before_xy_and_preserves_e(self):
        o,m,e,p,log=self.fixture()
        park_calibration(o,m,lambda:None,e,(0,0,0),(300,305,315))
        self.assertEqual([x[0] for x in log],[[150.,158.,5.,17.],[300.,305.,5.,17.]])
    def test_closed_contact_prevents_xy_park(self):
        o,m,e,p,log=self.fixture(closed=True)
        with self.assertRaisesRegex(ValueError,'PC7'):
            park_calibration(o,m,lambda:None,e,(0,0,0),(300,305,315))
        self.assertEqual(p,[150.,158.,5.,17.])
    def test_invalid_park_does_not_move(self):
        o,m,e,p,log=self.fixture(xy=(301,305))
        with self.assertRaisesRegex(ValueError,'travel'):
            park_calibration(o,m,lambda:None,e,(0,0,0),(300,305,315))
        self.assertEqual(log,[])
