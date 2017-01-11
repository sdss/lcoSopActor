"""
Test the various commands in SOP tccThread
"""

import unittest

from actorcore import TestHelper
import sopTester

import sopActor
from sopActor import Queue
import sopActor.myGlobals as myGlobals

from sopActor import tccThread

class TccThreadTester(sopTester.SopThreadTester):
    """subclass this, then unittest.TestCase, in that order."""
    def setUp(self, location='APO'):
        self.useThreads = []#[("master", sopActor.MASTER,  masterThread.main)]
        self.verbose = True
        super(TccThreadTester,self).setUp(location=location)
        # Do this after super setUp, as that's what creates actorState.
        myGlobals.actorState.queues['tcc'] = Queue('tcc')
        self.queues = myGlobals.actorState.queues


class TestAxisChecks(sopTester.SopTester, unittest.TestCase):
    """Test tccThread stop button and axis state functions"""
    def setUp(self):
        self.verbose = True
        super(TestAxisChecks,self).setUp()

    def _get_bad_axis_bits(self, tccState, expect):
        sopTester.updateModel('tcc',TestHelper.tccState[tccState])
        result = tccThread.get_bad_axis_bits(self.actorState.models['tcc'])
        self.assertEqual(result,expect)
    def test_get_bad_axis_bits_tracking(self):
        self._get_bad_axis_bits('tracking', [0,0,0])
    def test_get_bad_axis_bits_badAz(self):
        self._get_bad_axis_bits('badAz', [0x1800,0,0])
    def test_get_bad_axis_bits_stopped(self):
        self._get_bad_axis_bits('stopped', [0x2000,0x2000,0x2000])

    def test_axes_are_clear(self):
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        self.assertTrue(tccThread.axes_are_clear(self.actorState))
    def test_axes_are_clear_False(self):
        sopTester.updateModel('tcc',TestHelper.tccState['bad'])
        self.assertFalse(tccThread.axes_are_clear(self.actorState))

    def test_axes_are_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['slewing'])
        self.assertTrue(tccThread.axes_are_ok(self.actorState))
    def test_axes_are_ok_Halted_True(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted'])
        self.assertTrue(tccThread.axes_are_ok(self.actorState))
    def test_axes_are_ok_False(self):
        sopTester.updateModel('tcc',TestHelper.tccState['stopped'])
        self.assertFalse(tccThread.axes_are_ok(self.actorState))

    def test_check_stop_in(self):
        sopTester.updateModel('tcc',TestHelper.tccState['stopped'])
        self.assertTrue(tccThread.check_stop_in(self.actorState))
    def test_check_stop_in_False(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted'])
        self.assertFalse(tccThread.check_stop_in(self.actorState))

    def test_below_alt_limit_no(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted'])
        self.assertFalse(tccThread.below_alt_limit(self.actorState))
    def test_below_alt_limit_yes(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted_low'])
        self.assertTrue(tccThread.below_alt_limit(self.actorState))

    def _axes_state(self, axisCmdState, state, expect, axes=('az','alt','rot')):
        result = tccThread.axes_state(axisCmdState, state, axes=axes)
        self.assertEqual(result,expect,'wanted: %s, got: %s'%(state, axisCmdState))
    def test_axes_state_all_tracking(self):
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        axisCmdState = self.actorState.models['tcc'].keyVarDict['axisCmdState']
        self._axes_state(axisCmdState, 'tracking', True)
    def test_axes_state_all_tracking_not(self):
        sopTester.updateModel('tcc',TestHelper.tccState['badAz'])
        axisCmdState = self.actorState.models['tcc'].keyVarDict['axisCmdState']
        self._axes_state(axisCmdState, 'tracking', False)
    def test_axes_state_all_halt(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted_low'])
        axisCmdState = self.actorState.models['tcc'].keyVarDict['axisCmdState']
        self._axes_state(axisCmdState, 'halt', True)
    def test_axes_state_altrot_tracking(self):
        sopTester.updateModel('tcc',TestHelper.tccState['badAz'])
        axisCmdState = self.actorState.models['tcc'].keyVarDict['axisCmdState']
        self._axes_state(axisCmdState, 'slewing', True, axes=('alt','rot'))


class TestMcpSemaphoreOk(TccThreadTester, unittest.TestCase):
    def test_mcp_semaphore_ok(self):
        result = tccThread.mcp_semaphore_ok(self.cmd, self.actorState)
        self.assertEqual(result, 'None')
    def test_mcp_semaphore_ok_False(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['bad_semaphore'])
        result = tccThread.mcp_semaphore_ok(self.cmd, self.actorState)
        self.assertFalse(result)
        self._check_cmd(0,0,0,3,False)
    def test_mcp_semaphore_ok_no_semaphore(self):
        # empty list is the state if the keyword has not yet been issued.
        self.actorState.models['mcp'].keyVarDict['semaphoreOwner'].valueList = []
        result = tccThread.mcp_semaphore_ok(self.cmd, self.actorState)
        self.assertEqual(result, 'None')
        self._check_cmd(1,0,0,0,False)
    def test_mcp_semaphore_fails_no_semaphore(self):
        self.cmd.failOn = 'mcp sem.show'
        # empty list is the state if the keyword has not yet been issued.
        self.actorState.models['mcp'].keyVarDict['semaphoreOwner'].valueList = []
        result = tccThread.mcp_semaphore_ok(self.cmd, self.actorState)
        self.assertFalse(result)
        self._check_cmd(1,0,0,1,False)


class TestAxisInit(TccThreadTester, unittest.TestCase):
    """Test tccThread.axis_init()"""
    def _test_axis_init(self):
        tccThread.axis_init(self.cmd, self.actorState, self.queues['tcc'])
        msg = self.queues['tcc'].get()
        self.assertEqual(msg.type, sopActor.Msg.REPLY)
        return msg

    def test_axis_init_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        msg = self._test_axis_init()
        self.assertTrue(msg.success)
        self._check_cmd(2,1,0,0,False)
    def test_axis_init_no_init_needed(self):
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        sopTester.updateModel('mcp',TestHelper.mcpState['tcc_semaphore'])
        msg = self._test_axis_init()
        self.assertTrue(msg.success)
        self._check_cmd(1,1,0,0,False)
    def test_axis_init_alt_low(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted_low'])
        msg = self._test_axis_init()
        self.assertTrue(msg.success)
        self._check_cmd(2,1,1,0,False)


    def test_axis_init_no_axis_status(self):
        self.cmd.failOn = 'tcc axis status'
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        msg = self._test_axis_init()
        self.assertFalse(msg.success)
        self._check_cmd(1,0,0,2,False)
    def test_axis_init_stop_in(self):
        sopTester.updateModel('tcc',TestHelper.tccState['stopped'])
        msg = self._test_axis_init()
        self.assertFalse(msg.success)
        self._check_cmd(2,0,0,1,False)
    def test_axis_init_bad_semaphore(self):
        sopTester.updateModel('mcp',TestHelper.mcpState['bad_semaphore'])
        sopTester.updateModel('tcc',TestHelper.tccState['tracking'])
        msg = self._test_axis_init()
        self.assertFalse(msg.success)
        self._check_cmd(1,0,0,3,False)
    def test_axis_init_fails(self):
        self.cmd.failOn = 'tcc axis init'
        sopTester.updateModel('tcc',TestHelper.tccState['slewing'])
        msg = self._test_axis_init()
        self.assertFalse(msg.success)
        self._check_cmd(2,1,0,2,False)


class TestAxisStop(TccThreadTester, unittest.TestCase):
    def _axis_stop(self):
        tccThread.axis_stop(self.cmd, self.actorState, self.queues['tcc'])
        msg = self.queues['tcc'].get()
        self.assertEqual(msg.type, sopActor.Msg.REPLY)
        return msg

    def test_axis_stop(self):
        msg = self._axis_stop()
        self.assertTrue(msg.success)
        self._check_cmd(1,0,0,0, False)

    def test_axis_stop_fails(self):
        self.cmd.failOn = 'tcc axis stop'
        msg = self._axis_stop()
        self.assertFalse(msg.success)
        self._check_cmd(1,0,0,1, False, True)

class TestSlew(TccThreadTester, unittest.TestCase):
    def setUp(self):
        super(TestSlew,self).setUp()
        self.slewHandler = tccThread.SlewHandler(self.actorState, self.queues['tcc'])

    def test_parse_args_radecrot(self):
        ra, dec, rot = 10, 20, 30
        msg = sopActor.Msg(sopActor.Msg.SLEW, self.cmd, ra=ra, dec=dec, rot=rot, keepOffsets=True)
        self.slewHandler.parse_args(msg)
        self.assertEqual(self.slewHandler.ra, ra)
        self.assertEqual(self.slewHandler.dec, dec)
        self.assertEqual(self.slewHandler.rot, rot)
        self.assertTrue(self.slewHandler.keepOffsets)
    def test_parse_args_altazrot(self):
        alt, az, rot = 100, 200, 300
        msg = sopActor.Msg(sopActor.Msg.SLEW, self.cmd, alt=alt, az=az, rot=rot)
        self.slewHandler.parse_args(msg)
        self.assertEqual(self.slewHandler.alt, alt)
        self.assertEqual(self.slewHandler.az, az)
        self.assertEqual(self.slewHandler.rot, rot)
    def test_parse_args_keepOffsets(self):
        msg = sopActor.Msg(sopActor.Msg.SLEW, self.cmd, keepOffsets=True)
        self.slewHandler.parse_args(msg)
        self.assertTrue(self.slewHandler.keepOffsets)

    def _not_ok_to_slew(self, expect):
        result = self.slewHandler.not_ok_to_slew(self.cmd)
        self.assertEqual(result, expect)
    def test_not_ok_to_slew_halted_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted'])
        self._not_ok_to_slew(False)
    def test_not_ok_to_slew_halted_low_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['halted_low'])
        self._not_ok_to_slew(False)
    def test_not_ok_to_slew_stopped_not_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['stopped'])
        self._not_ok_to_slew(True)
    def test_not_ok_to_slew_bad_not_ok(self):
        sopTester.updateModel('tcc',TestHelper.tccState['bad'])
        self._not_ok_to_slew(True)

    def test_not_ok_to_slew_ignore_az_ok(self):
        """Start at low alt, pretend to move up, continued bad az should be ok."""
        sopTester.updateModel('tcc',TestHelper.tccState['halted_low'])
        self.slewHandler.not_ok_to_slew(self.cmd)
        sopTester.updateModel('tcc',TestHelper.tccState['badAz'])
        self._not_ok_to_slew(False)
        self._check_cmd(0,0,1,0,False)

    def _do_slew_radec(self, ra, dec, rot, success):
        self.slewHandler.ra = ra
        self.slewHandler.dec = dec
        self.slewHandler.rot = rot
        self.slewHandler.do_slew(self.cmd, self.queues['tcc'])
        msg = self.queues['tcc'].get(timeout=0.1)
        self.assertEqual(msg.success, success)
        error = 0 if success else 2
        self._check_cmd(1,1,0,error,False)
    def test_do_slew(self):
        self._do_slew_radec(10,20,30, True)
    def test_do_slew_fails(self):
        self.cmd.failOn = "tcc track 10.000000, 20.000000 icrs /rottype=object/rotang=30/rotwrap=mid"
        self._do_slew_radec(10,20,30, False)
    def test_do_slew_axis_goes_bad(self):
        """bad axis bit before calling tcc track, so it is in place."""
        sopTester.updateModel('tcc',TestHelper.tccState['badAz'])
        self._do_slew_radec(10,20,30, False)

    def _slew_altaz(self, alt, az, rot, tccState='tracking'):
        self.slewHandler.alt = alt
        self.slewHandler.az = az
        self.slewHandler.rot = rot
        sopTester.updateModel('tcc',TestHelper.tccState[tccState])
        self.slewHandler.slew(self.cmd, self.queues['tcc'])
        return self.queues['tcc'].get()
    def test_slew_altaz(self):
        msg = self._slew_altaz(100,200,300)
        self.assertTrue(msg.success)
        self._check_cmd(1,1,0,0,False)

    def test_slew_axis_stopped(self):
        sopTester.updateModel('tcc',TestHelper.tccState['stopped'])
        self.slewHandler.slew(self.cmd, self.queues['tcc'])
        msg = self.queues['tcc'].get(timeout=0.1)
        self.assertEqual(msg.type, sopActor.Msg.REPLY)
        self.assertFalse(msg.success)
        self._check_cmd(0,0,0,1,False,False)


class TestSlewLCO(TccThreadTester, unittest.TestCase):

    def setUp(self):

        super(TestSlewLCO, self).setUp(location='LCO')
        self.slewHandler = tccThread.SlewHandler(self.actorState,
                                                 self.queues['tcc'])

    def test_parse_args_radecrot(self):

        ra, dec, rot = 10, 20, None
        msg = sopActor.Msg(sopActor.Msg.SLEW,
                           self.cmd,
                           ra=ra, dec=dec, rot=rot,
                           keepOffsets=True)

        self.slewHandler.parse_args(msg)
        self.assertEqual(self.slewHandler.ra, ra)
        self.assertEqual(self.slewHandler.dec, dec)
        self.assertEqual(self.slewHandler.rot, rot)
        self.assertTrue(self.slewHandler.keepOffsets)
        self.assertTrue(self.slewHandler.moveScreen)

    def test_parse_args_moveScreen(self):

        msg = sopActor.Msg(sopActor.Msg.SLEW,
                           self.cmd,
                           moveScreen=False)

        self.slewHandler.parse_args(msg)
        self.assertFalse(self.slewHandler.moveScreen)

    def _do_slew_radec(self, ra, dec, success, moveScreen=True):

        self.slewHandler.ra = ra
        self.slewHandler.dec = dec
        self.slewHandler.rot = None
        self.slewHandler.moveScreen = moveScreen
        self.slewHandler.do_slew_lco(self.cmd, self.queues['tcc'])

        msg = self.queues['tcc'].get(timeout=0.1)
        self.assertEqual(msg.success, success)

        error = 0 if success else 1
        self._check_cmd(1, 1, 0, error, False)

    def test_do_slew(self):
        self._do_slew_radec(10, 20, True)

    def test_do_slew_fails(self):
        self.cmd.failOn = 'tcc target 10.000000, 20.000000 icrs /screen'
        self._do_slew_radec(10, 20, False)

    def test_do_slew_noScreen(self):
        self._do_slew_radec(10, 20, True, moveScreen=False)


if __name__ == '__main__':
    verbosity = 2

    suite = None
    # to test just one piece
    # suite = unittest.TestLoader().loadTestsFromTestCase(TestSlew)

    if suite:
        unittest.TextTestRunner(verbosity=verbosity).run(suite)
    else:
        unittest.main(verbosity=verbosity)
