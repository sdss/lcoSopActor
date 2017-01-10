# !usr/bin/env python2
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2016-06-10 13:00:58
# @Last modified by:   Brian
# @Last Modified time: 2016-06-10 13:05:43

from __future__ import print_function, division, absolute_import

import opscore.protocols.keys as keys
import opscore.protocols.types as types
from opscore.utility.qstr import qstr

import sopActor
from sopActor import CmdState, Msg
import sopActor.myGlobals as myGlobals
from sopActor.Commands import SopCmd


class SopCmd_LCO(SopCmd.SopCmd):

    def __init__(self, actor):

        # initialize from the superclass
        super(SopCmd_LCO, self).__init__(actor)

        # Define APO specific keys.
        self.keys.extend([])

        # Define new commands for APO
        self.vocab = [
            ('gotoField', '[<guiderFlatTime>] [<guiderTime>] [noGuider]'
                          '[abort]', self.gotoField)]

    def gotoField(self, cmd):
        """Slew to the current cartridge/pointing.

        Slew to the position of the currently loaded cartridge. Eventually
        this command may also do callibrations.

        """

        sopState = myGlobals.actorState
        cmdState = sopState.gotoField
        survey = sopState.survey
        keywords = cmd.cmd.keywords

        if self.doing_science(sopState):
            cmd.fail('text=\"A science exposure sequence is running -- '
                     'will not go to field!\"')
            return

        if 'abort' in keywords:
            self.stop_cmd(cmd, cmdState, sopState, 'gotoField')
            return

        cmdState.reinitialize(cmd, output=False)

        cmdState.doSlew = 'noSlew' not in keywords

        if survey == sopActor.UNKNOWN:
            cmd.warn(
                'text="No cartridge is known to be loaded; disabling guider"')
            cmdState.doGuider = False
            cmdState.doGuiderFlat = False

        if cmdState.doSlew:
            pointingInfo = sopState.models['platedb'].keyVarDict['pointingInfo']
            cmdState.ra = pointingInfo[3]
            cmdState.dec = pointingInfo[4]
            # Not setting the rotator because at LCO we don't move it.

        if myGlobals.bypass.get(name='slewToField'):
            fakeSkyPos = SopCmd.obs2Sky(cmd, cmdState.fakeAz, cmdState.fakeAlt,
                                        cmdState.fakeRotOffset)
            cmdState.ra = fakeSkyPos[0]
            cmdState.dec = fakeSkyPos[1]
            cmd.warn('text=\"Bypass slewToField is FAKING RA DEC:  '
                     '%g, %g\"' % (cmdState.ra, cmdState.dec))

        activeStages = []
        if cmdState.doSlew:
            activeStages.append('slew')
        activeStages.append('cleanup')  # we always may have to cleanup...
        cmdState.setupCommand(cmd, activeStages)

        sopState.queues[sopActor.MASTER].put(Msg.GOTO_FIELD,
                                             cmd,
                                             replyQueue=self.replyQueue,
                                             actorState=sopState,
                                             cmdState=cmdState)

    def initCommands(self):
        """Recreate the objects that hold the state of the various commands."""

        sopState = myGlobals.actorState

        sopState.gotoField = CmdState.GotoFieldCmd()

        super(SopCmd_LCO, self).initCommands()

    def _status_commands(self, cmd, sopState, oneCommand=None):
        """Status of LCO specific commands.

        """

        super(SopCmd_LCO, self)._status_commands(cmd, sopState,
                                                 oneCommand=oneCommand)

        sopState.gotoField.genKeys(cmd=cmd, trimKeys=oneCommand)

    def doing_science(self, sopState):
        """Return True if any sort of science command is currently running."""

        return (sopState.doApogeeScience.cmd and
                sopState.doApogeeScience.cmd.isAlive())
