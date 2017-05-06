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

import sopActor
from sopActor import CmdState, Msg
import sopActor.myGlobals as myGlobals
from sopActor.Commands import SopCmd


class SopCmd_LCO(SopCmd.SopCmd):

    def __init__(self, actor):

        # initialize from the superclass
        super(SopCmd_LCO, self).__init__(actor)

        # Define APO specific keys.
        self.keys.extend([keys.Key('nDarks', types.Int(), help='Number of darks to take'),
                          keys.Key('nDarkReads', types.Int(), help='Number of readouts per dark')])

        # Define new commands for APO
        self.vocab = [('gotoField', '[slew] [screen] [flat] [guiderFlat] '
                                    '[darks] [guider] '
                                    '[<guiderFlatTime>] [<guiderTime>] [<nDarks>] '
                                    '[<nDarkReads>] [abort]', self.gotoField)]

    def _get_keyword_value(self, keywords, param, default=None, nn=0):
        """A convenience function to get values from keywords."""

        if param in keywords:
            return keywords[param].values[nn]
        else:
            if default is not None:
                return default
            else:
                raise ValueError('keyword {0} is undefined and no default was given.'.format(param))

    def gotoField(self, cmd):
        """Slew to the current cartridge/pointing.

        Slew to the position of the currently loaded cartridge. Eventually
        this command may also do calibrations.

        """

        sopState = myGlobals.actorState
        cmdState = sopState.gotoField
        keywords = cmd.cmd.keywords

        if self.doing_science(sopState):
            cmd.fail('text=\"A science exposure sequence is running -- '
                     'will not go to field!\"')
            return

        if 'abort' in keywords:
            self.stop_cmd(cmd, cmdState, sopState, 'gotoField')
            return

        survey = sopState.survey

        if survey == sopActor.UNKNOWN:
            cmd.fail('text="No cartridge is known to be loaded; disabling guider"')
            return

        # Modify running gotoField command
        if self.modifiable(cmd, cmdState):

            cmd.warn('text="modifying gotoField command"')

            cmdState.doSlew = True if 'slew' in keywords else False
            cmdState.doScreen = True if 'screen' in keywords else False
            cmdState.doGuiderFlat = True if 'guiderFlat' in keywords else False
            cmdState.doGuider = True if 'guider' in keywords else False
            cmdState.doDarks = True if 'darks' in keywords else False
            cmdState.doFlat = True if 'flat' in keywords else False

            if 'guiderFlatTime' in keywords:
                cmdState.guiderFlatTime = float(keywords['guiderFlatTime'].values[0])
            if 'guiderTime' in keywords:
                cmdState.guiderTime = float(keywords['guiderTime'].values[0])
            if 'nDarks' in keywords:
                cmdState.nDarks = float(keywords['nDarks'].values[0])
            if 'nDarkReads' in keywords:
                cmdState.nDarks = float(keywords['nDarkReads'].values[0])

            cmdState.setStageState('slew', 'pending' if cmdState.doSlew else 'off')
            cmdState.setStageState('screen', 'pending' if cmdState.doScreen else 'off')
            cmdState.setStageState('guider', 'pending' if cmdState.doGuider else 'off')
            cmdState.setStageState('darks', 'pending' if cmdState.doDarks else 'off')
            cmdState.setStageState('flat', 'pending' if cmdState.doFlat else 'off')
            cmdState.setStageState('guiderFlat', 'pending' if cmdState.doGuiderFlat else 'off')

            self.status(cmd, threads=False, finish=True, oneCommand='gotoField')

            return

        cmdState.reinitialize(cmd, output=False)

        cmdState.doSlew = True if 'slew' in keywords else False
        cmdState.doScreen = True if 'screen' in keywords else False
        cmdState.doGuiderFlat = True if 'guiderFlat' in keywords else False
        cmdState.doGuider = True if 'guider' in keywords else False
        cmdState.doDarks = True if 'darks' in keywords else False
        cmdState.doFlat = True if 'flat' in keywords else False

        activeStages = []

        if cmdState.doSlew or cmdState.doScreen:
            # We are going to "slew" also if we want to move the screen.
            # TODO: if doSlew is False and doScreen is True, should we use the
            # current RA/Dec instead of the field ones?
            pointingInfo = sopState.models['platedb'].keyVarDict['pointingInfo']
            cmdState.ra = pointingInfo[3]
            cmdState.dec = pointingInfo[4]
            cmdState.rotang = 0.0  # Rotator angle; should always be 0.0

            if cmdState.doSlew:
                activeStages.append('slew')

        if cmdState.doScreen:
            activeStages.append('screen')

        if cmdState.doFlat:
            activeStages.append('flat')

        if cmdState.doDarks:
            cmdState.nDarks = int(self._get_keyword_value(keywords, 'nDarks', default=2))
            cmdState.nDarkReads = int(self._get_keyword_value(keywords, 'nDarkReads', default=10))
            activeStages.append('darks')

        if cmdState.doGuiderFlat:
            cmdState.guiderFlatTime = float(self._get_keyword_value(keywords, 'guiderFlatTime',
                                                                    default=20))
            cmdState.doGuiderFlat = cmdState.guiderFlatTime > 0
            activeStages.append('guiderFlat')

        if cmdState.doGuider:
            cmdState.guiderTime = float(self._get_keyword_value(keywords, 'guiderTime', default=5))
            activeStages.append('guider')

        activeStages.append('cleanup')  # we always may have to cleanup...
        cmdState.setupCommand(cmd, activeStages)

        sopState.queues[sopActor.MASTER].put(Msg.GOTO_FIELD, cmd, replyQueue=self.replyQueue,
                                             actorState=sopState, cmdState=cmdState)

    def initCommands(self):
        """Recreate the objects that hold the state of the various commands."""

        sopState = myGlobals.actorState

        sopState.gotoField = CmdState.GotoFieldLCOCmd()

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
