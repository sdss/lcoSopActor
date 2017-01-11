"""
Tests of the SopCmd functions, without executing any threads.

Each of these tests should confirm that a SopCmd command call calls the correct
queue with an appropriately crafted CmdState and other relevant parameters.

If these tests work correctly, each masterThread function should work
correctly when called via a SopCmd (assuming test_masterThread clears).

This version tests LCO specific commands.

"""

import unittest
import threading

import sopActor
import sopActor.myGlobals as myGlobals
from sopActor import Queue

from actorcore import TestHelper
import sopTester


def build_active_stages(allStages, activeStages):
    """Returns a dictionary of stages and their off/pending state."""

    stages = dict(zip(allStages, ['off'] * len(allStages)))
    for x in activeStages:
        stages[x] = 'pending'

    return stages


class SopCmdTester(sopTester.SopTester):

    def setUp(self):

        self.verbose = True
        super(SopCmdTester, self).setUp(location='LCO')
        self.timeout = 1

        # Do this after super setUp, as that's what creates actorState.
        myGlobals.actorState.queues = {}
        myGlobals.actorState.queues[sopActor.MASTER] = Queue('master')
        myGlobals.actorState.queues[sopActor.TCC] = Queue('tcc')
        myGlobals.actorState.queues[sopActor.SLEW] = Queue('slew')

        self.cmd.verbose = False  # don't spam initial loadCart messages
        self.cmd.clear_msgs()
        self.cmd.verbose = self.verbose
        self._clear_bypasses()

    def _pre_command(self, command, queue):
        """Run a text command in advance without being verbose.

        Clears any message.

        """

        self.cmd.verbose = False
        self._run_cmd(command, queue)
        self.cmd.clear_msgs()
        self.cmd.verbose = self.verbose

        # in case the above command "finishes"
        self.cmd = TestHelper.Cmd(verbose=self.verbose)

    def _start_thread(self, queue, tid, tname):
        """Start a fakeThread for queue, returning the threading instance."""

        actorState = self.actorState
        actorState.threads = {}
        actorState.threads[tid] = threading.Thread(target=sopTester.FakeThread,
                                                   name=tname,
                                                   args=[actorState.actor,
                                                         actorState.queues])
        actorState.threads[tid].daemon = True
        actorState.threads[tid].start()

    def _stop_thread(self, queue, tid):
        """Stop thread tid associated with queue, and cleanup."""

        queue.put(sopActor.Msg(sopActor.Msg.EXIT, self.cmd))
        self.actorState.threads[tid].join()


class TestNoBoss(SopCmdTester, unittest.TestCase):
    """Tests that the APO specific commands are not present."""

    # TODO: this is just a draft. Add more tests.

    def test_noCollimateBoss(self):
        self.assertFalse(hasattr(self.sopCmd, 'collimateBoss'))


class TestGotoField(SopCmdTester, unittest.TestCase):

    def _gotoField(self, cart, expect, stages, args, cmd_levels=(0, 2, 0, 0)):

        allStages = ['slew', 'guider', 'cleanup']

        stages = build_active_stages(allStages, stages)

        self._update_cart(cart, 'APOGEE')

        queue = myGlobals.actorState.queues[sopActor.MASTER]

        msg = self._run_cmd('gotoField %s' % (args), queue)

        self.assertEqual(msg.type, sopActor.Msg.GOTO_FIELD)

        self.assertEqual(msg.cmdState.stages, stages)
        self._check_levels(*cmd_levels)

        self.assertEqual(msg.cmdState.ra, expect.get('ra', 0))
        self.assertEqual(msg.cmdState.dec, expect.get('dec', 0))
        self.assertEqual(msg.cmdState.doSlew, expect.get('doSlew', True))
        self.assertEqual(msg.cmdState.moveScreen, expect.get('moveScreen', True))

    def test_gotoField_apogee_default(self):

        sopTester.updateModel('guider', TestHelper.guiderState['apogeeLoaded'])
        sopTester.updateModel('platedb', TestHelper.platedbState['apogee'])

        stages = ['slew', 'cleanup']

        expect = {'ra': 20, 'dec': 30}

        self._gotoField(1, expect, stages, '')

    def test_gotoField_abort(self):

        self.actorState.gotoField.cmd = self.cmd
        self._run_cmd('gotoField abort', None)
        self.assertTrue(self.actorState.aborting)

    def test_gotoField_noScreen(self):

        sopTester.updateModel('guider', TestHelper.guiderState['apogeeLoaded'])
        sopTester.updateModel('platedb', TestHelper.platedbState['apogee'])
        stages = ['slew', 'cleanup']
        expect = {'ra': 20, 'dec': 30, 'moveScreen': False}

        self._gotoField(1, expect, stages, 'noScreen')


if __name__ == '__main__':

    verbosity = 2
    suite = None

    if suite:
        unittest.TextTestRunner(verbosity=verbosity).run(suite)
    else:
        unittest.main(verbosity=verbosity)
