#!/usr/bin/env python

""" Wrap top-level ICC functions. """

import threading

import opscore.protocols.keys as keys
import opscore.protocols.types as types

from opscore.utility.qstr import qstr

import glob
import os

from sopActor import CmdState, Msg
import sopActor
import sopActor.myGlobals as myGlobals
from sopActor.multiCommand import MultiCommand

# -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-


# SDSS-IV plates should all be "APOGEE-2;MaNGA", but we need both,
# for test plates drilled as part of SDSS-III.
survey_dict = {'UNKNOWN': sopActor.UNKNOWN,
               'ecamera': sopActor.ECAMERA,
               'BOSS': sopActor.BOSS,
               'eBOSS': sopActor.BOSS,
               'APOGEE': sopActor.APOGEE,
               'APOGEE-2': sopActor.APOGEE,
               'APOGEE-2S': sopActor.APOGEE2S,
               'MaNGA': sopActor.MANGA,
               'APOGEE-2&MaNGA': sopActor.APOGEEMANGA,
               'APOGEE&MaNGA': sopActor.APOGEEMANGA}

surveyMode_dict = {'None': None,
                   None: None,
                   'APOGEE lead': sopActor.APOGEELEAD,
                   'MaNGA dither': sopActor.MANGADITHER,
                   'MaNGA stare': sopActor.MANGASTARE}

# And the inverses of the above.
# Can't directly make an inverse, since it's not one-to-one.
survey_inv_dict = {sopActor.UNKNOWN: 'UNKNOWN',
                   sopActor.ECAMERA: 'ecamera',
                   sopActor.BOSS: 'eBOSS',
                   sopActor.APOGEE: 'APOGEE-2',
                   sopActor.APOGEE2S: 'APOGEE-2S',
                   sopActor.MANGA: 'MaNGA',
                   sopActor.APOGEEMANGA: 'APOGEE-2&MaNGA'}

surveyMode_inv_dict = {None: 'None',
                       sopActor.MANGADITHER: 'MaNGA dither',
                       sopActor.MANGASTARE: 'MaNGA stare',
                       sopActor.APOGEELEAD: 'APOGEE lead'}


class SopCmd(object):
    """ Wrap commands to the sop actor"""

    def __init__(self, actor):
        self.actor = actor
        self.replyQueue = sopActor.Queue('(replyQueue)',0)
        #
        # Declare keys that we're going to use
        #
        self.keys = keys.KeysDictionary(
            "sop_sop", (2, 0),
            keys.Key("abort", help="Abort a command"),
            keys.Key("clear", help="Clear a flag"),
            keys.Key("expTime", types.Float(), help="Exposure time"),
            keys.Key("fiberId", types.Int(), help="A fiber ID"),
            keys.Key("keepQueues", help="Restart thread queues"),
            keys.Key("noSlew", help="Don't slew to field"),
            keys.Key("noDomeFlat", help="Don't run the dome flat step"),
            keys.Key("geek", help="Show things that only some of us love"),
            keys.Key("subSystem", types.String()*(1,), help="The sub-systems to bypass"),
            keys.Key("threads", types.String()*(1,), help="Threads to restart; default: all"),
            keys.Key("ditherPairs", types.Int(),
                     help="Number of dither pairs (AB or BA) to observe"),
            keys.Key('guiderTime', types.Float(), help='Exposure time '
                                                       'for guider'),
            keys.Key('guiderFlatTime', types.Float(), help='Exposure time '
                                                           'for guider flats'),
            keys.Key('noGuider', help='Don\'t start the guider'),
            keys.Key("comment", types.String(), help="comment for headers"),
            keys.Key("scriptName", types.String(), help="name of script to run"),
            keys.Key("az", types.Float(), help="what azimuth to slew to"),
            keys.Key("rotOffset", types.Float(), help="what rotator offset to add"),
            keys.Key("alt", types.Float(), help="what altitude to slew to"),
                                        )
        #
        # Declare commands
        #
        self.vocab = [
            ("bypass", "<subSystem> [clear]", self.bypass),
            ("doApogeeScience", "[<expTime>] [<ditherPairs>] [stop] [<abort>] [<comment>]", self.doApogeeScience),
            ("doApogeeSkyFlats", "[<expTime>] [<ditherPairs>] [stop] [abort]", self.doApogeeSkyFlats),
            ("ping", "", self.ping),
            ("restart", "[<threads>] [keepQueues]", self.restart),
            ("gotoInstrumentChange", "[abort] [stop]", self.gotoInstrumentChange),
            ("gotoStow", "[abort] [stop]", self.gotoStow),
            ("gotoAll60", "[abort] [stop]", self.gotoAll60),
            ("gotoStow60", "[abort] [stop]", self.gotoStow60),
            ("gotoGangChange", "[<alt>] [abort] [stop] [noDomeFlat] [noSlew]", self.gotoGangChange),
            ("doApogeeDomeFlat", "[stop] [abort]", self.doApogeeDomeFlat),
            ("setFakeField", "[<az>] [<alt>] [<rotOffset>]", self.setFakeField),
            ("status", "[geek]", self.status),
            ("reinit", "", self.reinit),
            ("runScript", "<scriptName>", self.runScript),
            ("listScripts", "", self.listScripts),
            ]

    def stop_cmd(self, cmd, cmdState, sopState, name):
        """Stop an active cmdState, failing if there's nothing to stop."""
        if self.modifiable(cmd, cmdState):
            cmdState.abort()
            if cmdState.cmd:
                cmdState.cmd.fail('aborted command.')
            self.status(cmd, threads=False, finish=True, oneCommand=name)
        else:
            cmd.fail('text="No %s command is active"'%(name))

    def modifiable(self, cmd, cmdState):
        return cmdState.cmd and cmdState.cmd.isAlive()

    def doApogeeScience(self, cmd):
        """Take a sequence of dithered APOGEE science frames, or stop or modify a running sequence."""

        sopState = myGlobals.actorState
        cmdState = sopState.doApogeeScience
        keywords = cmd.cmd.keywords
        name = 'doApogeeScience'

        if "stop" in keywords or 'abort' in keywords:
            self.stop_cmd(cmd, cmdState, sopState, name)
            return

        # Modify running doApogeeScience command
        if self.modifiable(cmd, cmdState):
            if "ditherPairs" in keywords:
                cmdState.set('ditherPairs',int(keywords["ditherPairs"].values[0]))

            if "expTime" in keywords:
                cmdState.set('expTime',int(keywords["expTime"].values[0]))

            self.status(cmd, threads=False, finish=True, oneCommand=name)
            return

        cmdState.reinitialize(cmd)
        ditherPairs = int(keywords["ditherPairs"].values[0]) if "ditherPairs" in keywords else None
        cmdState.set('ditherPairs',ditherPairs)
        comment = keywords["comment"].values[0] if "comment" in keywords else None
        cmdState.comment = comment
        expTime = float(keywords["expTime"].values[0]) if "expTime" in keywords else None
        cmdState.set('expTime', expTime)

        if cmdState.ditherPairs == 0:
            cmd.fail('text="You must take at least one exposure"')
            return

        sopState.queues[sopActor.MASTER].put(Msg.DO_APOGEE_EXPOSURES, cmd, replyQueue=self.replyQueue,
                                             actorState=sopState, cmdState=cmdState)

    def doApogeeSkyFlats(self, cmd):
        """Take a set of APOGEE sky flats, offsetting by 0.01 degree in RA."""

        sopState = myGlobals.actorState
        cmdState = sopState.doApogeeSkyFlats
        keywords = cmd.cmd.keywords
        name = 'doApogeeSkyFlats'

        blocked = self.isSlewingDisabled(cmd)
        if blocked:
            cmd.fail('text=%s' % (qstr('will not take APOGEE sky flats: %s' % (blocked))))
            return

        if "stop" in cmd.cmd.keywords or 'abort' in cmd.cmd.keywords:
            self.stop_cmd(cmd, cmdState, sopState, name)
            return

        if self.modifiable(cmd, cmdState):
            if "ditherPairs" in keywords:
                cmdState.set('ditherPairs',int(keywords["ditherPairs"].values[0]))

            if "expTime" in keywords:
                cmdState.set('expTime',int(keywords["expTime"].values[0]))

            self.status(cmd, threads=False, finish=True, oneCommand=name)
            return
        cmdState.reinitialize(cmd)

        expTime = float(keywords["expTime"].values[0]) if "expTime" in keywords else None
        cmdState.set('expTime', expTime)
        ditherPairs = int(keywords["ditherPairs"].values[0]) if "ditherPairs" in keywords else None
        cmdState.set('ditherPairs',ditherPairs)

        if cmdState.ditherPairs == 0:
            cmd.fail('text="You must take at least one exposure"')
            return

        cmdState.setCommandState('running')

        sopState.queues[sopActor.MASTER].put(Msg.DO_APOGEE_SKY_FLATS, cmd, replyQueue=self.replyQueue,
                                             actorState=sopState, cmdState=cmdState)

    def bypass(self, cmd):
        """Ignore errors in a subsystem, or force a system to be in a given state."""
        subSystems = cmd.cmd.keywords["subSystem"].values
        doBypass = False if "clear" in cmd.cmd.keywords else True

        sopState = myGlobals.actorState
        bypass = myGlobals.bypass

        for subSystem in subSystems:
            if bypass.set(subSystem, doBypass) is None:
                cmd.fail('text="{} is not a recognised and bypassable subSystem"'.format(subSystem))
                return
            if bypass.is_cart_bypass(subSystem):
                self.updateCartridge(sopState.cartridge, sopState.plateType, sopState.surveyModeName, status=False, bypassed=True)
                cmdStr = 'setRefractionBalance plateType="{0}" surveyMode="{1}"'.format(*sopState.surveyText)
                cmdVar = sopState.actor.cmdr.call(actor="guider", forUserCmd=cmd, cmdStr=cmdStr)
                if cmdVar.didFail:
                    cmd.fail('text="Failed to set guider refraction balance for bypass {0} {1}'.format(subSystem, doBypass))
                    return
            if bypass.is_gang_bypass(subSystem):
                cmd.warn('text="gang bypassed: {}"'.format(sopState.apogeeGang.getPos()))

        self.status(cmd, threads=False)

    def setFakeField(self, cmd):
        """ (Re)set the position gotoField slews to if the slewToField bypass is set.

        The az and alt are used directly. RotOffset is added to whatever obj offset is calculated
        for the az and alt.

        Leaving any of the az, alt, and rotOffset arguments off will set them to the default, which is 'here'.
        """

        sopState = myGlobals.actorState

        cmd.warn('text="cmd=%s"' % (cmd.cmd.keywords))

        sopState.gotoField.fakeAz = float(cmd.cmd.keywords["az"].values[0]) if "az" in cmd.cmd.keywords else None
        sopState.gotoField.fakeAlt = float(cmd.cmd.keywords["alt"].values[0]) if "alt" in cmd.cmd.keywords else None
        sopState.gotoField.fakeRotOffset = float(cmd.cmd.keywords["rotOffset"].values[0]) if "rotOffset" in cmd.cmd.keywords else 0.0

        cmd.finish('text="set fake slew position to az=%s alt=%s rotOffset=%s"'
                   % (sopState.gotoField.fakeAz,
                      sopState.gotoField.fakeAlt,
                      sopState.gotoField.fakeRotOffset))

    def gotoPosition(self, cmd, name, az, alt, rot):
        """Goto a specified alt/az/[rot] position, named 'name'."""

        sopState = myGlobals.actorState
        cmdState = sopState.gotoPosition
        keywords = cmd.cmd.keywords

        blocked = self.isSlewingDisabled(cmd)
        if blocked:
            cmd.fail('text=%s' %
                     (qstr('will not {0}: {1}'.format(name, blocked))))
            return

        if 'stop' in keywords or 'abort' in keywords:
            self.stop_cmd(cmd, cmdState, sopState, 'gotoPosition')
            return

        if self.modifiable(cmd, cmdState):
            # Modify running gotoPosition command
            cmd.fail('text="Cannot modify {0}."'.format(name))
            return

        cmdState.reinitialize(cmd, output=False)
        cmdState.set('alt', alt)
        cmdState.set('az', az)
        cmdState.set('rot', rot)

        activeStages = ['slew']
        cmdState.setupCommand(cmd, activeStages)

        sopState.queues[sopActor.SLEW].put(
            Msg.GOTO_POSITION, cmd, replyQueue=self.replyQueue,
            actorState=sopState, cmdState=cmdState)

    def gotoInstrumentChange(self, cmd):
        """Go to the instrument change position: alt=90 az=121 rot=0"""

        self.gotoPosition(cmd, "instrument change", 121, 90, 0)

    def gotoStow(self, cmd):
        """Go to the stow position: alt=30, az=121, rot=0"""

        self.gotoPosition(cmd, "stow", 121, 30, 0)

    def gotoAll60(self, cmd):
        """Go to the startup check position: alt=60, az=60, rot=60"""

        self.gotoPosition(cmd, "stow", 60, 60, 60)

    def gotoStow60(self, cmd):
        """Go to the resting position: alt=60, az=121, rot=0"""

        self.gotoPosition(cmd, "stow", 121, 60, 0)

    def gotoGangChange(self, cmd):
        """Go to the gang connector change position"""

        sopState = myGlobals.actorState
        cmdState = sopState.gotoGangChange
        keywords = cmd.cmd.keywords

        blocked = self.isSlewingDisabled(cmd)
        if blocked:
            cmd.fail('text=%s' % (qstr('will not go to gang change: %s' % (blocked))))
            return

        if 'stop' in keywords or 'abort' in keywords:
            self.stop_cmd(cmd, cmdState, sopState, 'gotoGangChange')
            return

        if self.modifiable(cmd, cmdState):
            # Modify running gotoGangChange command
            cmd.fail('text="Cannot modify gotoGangChange."')
            return

        cmdState.reinitialize(cmd, output=False)
        alt = keywords["alt"].values[0] if "alt" in keywords else None
        cmdState.set('alt',alt)
        cmdState.doSlew = "noSlew" not in keywords
        cmdState.doDomeFlat = "noDomeFlat" not in keywords

        activeStages = []
        if cmdState.doSlew: activeStages.append('slew')
        if cmdState.doDomeFlat: activeStages.append('domeFlat')
        cmdState.setupCommand(cmd, activeStages)

        sopState.queues[sopActor.SLEW].put(Msg.GOTO_GANG_CHANGE, cmd, replyQueue=self.replyQueue,
                                           actorState=sopState, cmdState=cmdState)

    def doApogeeDomeFlat(self, cmd):
        """Take an APOGEE dome flat, with FFS closed and FFlamps on."""
        sopState = myGlobals.actorState
        cmdState = sopState.doApogeeDomeFlat

        if self.doing_science(sopState):
            cmd.fail("text='A science exposure sequence is running -- will not take a dome flat!")
            return

        if 'stop' in cmd.cmd.keywords or 'abort' in cmd.cmd.keywords:
            self.stop_cmd(cmd, cmdState, sopState, 'doApogeeDomeFlat')
            return

        if self.modifiable(cmd, cmdState):
            # Modify running doApogeeDomeFlat command
            cmd.fail('text="Cannot modify doApogeeDomeFlat."')
            return

        cmdState.reinitialize(cmd)

        sopState.queues[sopActor.SLEW].put(Msg.DO_APOGEE_DOME_FLAT, cmd, replyQueue=self.replyQueue,
                                           actorState=sopState, cmdState=cmdState,
                                           survey=sopState.survey)

    def runScript(self, cmd):
        """ Run the named script from the SOPACTOR_DIR/scripts directory. """
        sopState = myGlobals.actorState

        sopState.queues[sopActor.SCRIPT].put(Msg.NEW_SCRIPT, cmd, replyQueue=self.replyQueue,
                                             actorState=sopState,
                                             survey=sopState.survey,
                                             scriptName = cmd.cmd.keywords["scriptName"].values[0])

    def listScripts(self, cmd):
        """ List available script names for the runScript command."""
        path = os.path.join(os.environ['SOPACTOR_DIR'],'scripts','*.inp')
        scripts = glob.glob(path)
        scripts = ','.join(os.path.splitext(os.path.basename(s))[0] for s in scripts)
        cmd.inform('availableScripts="%s"'%scripts)
        cmd.finish('')

    def ping(self, cmd):
        """ Query sop for liveness/happiness. """

        cmd.finish('text="Yawn; how soporific"')

    def restart(self, cmd):
        """Restart the worker threads"""

        sopState = myGlobals.actorState

        threads = cmd.cmd.keywords["threads"].values if "threads" in cmd.cmd.keywords else None
        keepQueues = True if "keepQueues" in cmd.cmd.keywords else False

        if threads == ["pdb"]:
            cmd.warn('text="The sopActor is about to break to a pdb prompt"')
            import pdb; pdb.set_trace()
            cmd.finish('text="We now return you to your regularly scheduled sop session"')
            return


        if sopState.restartCmd:
            sopState.restartCmd.finish("text=\"secundum verbum tuum in pace\"")
            sopState.restartCmd = None
        #
        # We can't finish this command now as the threads may not have died yet,
        # but we can remember to clean up _next_ time we restart
        #
        cmd.inform("text=\"Restarting threads\"")
        sopState.restartCmd = cmd

        sopState.actor.startThreads(sopState, cmd, restart=True,
                                    restartThreads=threads, restartQueues=not keepQueues)

    def reinit(self, cmd):
        """ (engineering command) Recreate the objects which hold the state of the various top-level commands. """

        cmd.inform('text="recreating command objects"')
        try:
            self.initCommands()
        except Exception as e:
            cmd.fail('text="failed to re-initialize command state: %s"'%e)
            return

        cmd.finish('')

    def isSlewingDisabled(self, cmd):
        """Return False if we can slew, otherwise return a string describing why we cannot."""
        sopState = myGlobals.actorState

        if sopState.survey == sopActor.BOSS:
            return sopState.doBossScience.isSlewingDisabled()

        elif sopState.survey == sopActor.MANGA:
            disabled1 = sopState.doMangaDither.isSlewingDisabled()
            disabled2 = sopState.doMangaSequence.isSlewingDisabled()
            return disabled1 if disabled1 else disabled2

        elif sopState.survey == sopActor.APOGEE:
            disabled1 = sopState.doApogeeScience.isSlewingDisabled()
            disabled2 = sopState.doApogeeSkyFlats.isSlewingDisabled()
            return disabled1 if disabled1 else disabled2

        elif sopState.survey == sopActor.APOGEEMANGA:
            disabled1 = sopState.doApogeeMangaDither.isSlewingDisabled()
            disabled2 = sopState.doApogeeMangaSequence.isSlewingDisabled()
            return disabled1 if disabled1 else disabled2

        return False

    def status(self, cmd, threads=False, finish=True, oneCommand=None):
        """Return sop status.

        If threads is true report on SOP's threads; (also if geek in cmd.keywords)
        If finish complete the command.
        Trim output to contain just keys relevant to oneCommand.
        """

        sopState = myGlobals.actorState
        bypass = myGlobals.bypass

        self.actor.sendVersionKey(cmd)

        if hasattr(cmd, 'cmd') and cmd.cmd != None and "geek" in cmd.cmd.keywords:
            threads = True
            for t in threading.enumerate():
                cmd.inform('text="%s"' % t)

        bypassNames, bypassStates = bypass.get_bypass_list()
        cmd.inform("bypassNames="+", ".join(bypassNames))
        bypassed = bypass.get_bypassedNames()
        txt = "bypassedNames=" + ", ".join(bypassed)
        # output non-empty bypassedNames as a warning, per #2187.
        if bypassed == []:
            cmd.inform(txt)
        else:
            cmd.warn(txt)
        cmd.inform('text="apogeeGang: %s"' % (sopState.apogeeGang.getPos()))

        cmd.inform("surveyCommands=" + ", ".join(sopState.validCommands))

        self._status_commands(cmd, sopState, oneCommand=oneCommand)

        if threads:
            self._status_threads(cmd, sopState, finish=finish)

        if finish:
            cmd.finish("")

        return

    def _status_commands(self, cmd, sopState, oneCommand=None):
        """Status of commands.

        This method is intended to be super'd and expanded for each location.

        """

        # major commands
        sopState.doApogeeScience.genKeys(cmd=cmd, trimKeys=oneCommand)
        sopState.doApogeeSkyFlats.genKeys(cmd=cmd, trimKeys=oneCommand)
        sopState.gotoGangChange.genKeys(cmd=cmd, trimKeys=oneCommand)
        sopState.doApogeeDomeFlat.genKeys(cmd=cmd, trimKeys=oneCommand)
        sopState.gotoPosition.genKeys(cmd=cmd, trimKeys=oneCommand)

    def _status_threads(self, cmd, sopState, finish=True):
        # TBD: threads arg is only used with "geek" option, apparently?
        # TBD: I guess its useful for live debugging of the threads.

        try:
            sopState.ignoreAborting = True
            getStatus = MultiCommand(cmd, 5.0, None)

            for tid in sopState.threads.keys():
                getStatus.append(tid, Msg.STATUS)

            if not getStatus.run():
                if finish:
                    cmd.fail("")
                    return
                else:
                    cmd.warn("")
        finally:
            sopState.ignoreAborting = False

    def initCommands(self):
        """Recreate the objects that hold the state of the various commands."""

        sopState = myGlobals.actorState

        sopState.doApogeeScience = CmdState.DoApogeeScienceCmd()
        sopState.doApogeeSkyFlats = CmdState.DoApogeeSkyFlatsCmd()
        sopState.gotoGangChange = CmdState.GotoGangChangeCmd()
        sopState.gotoPosition = CmdState.GotoPositionCmd()
        sopState.doApogeeDomeFlat = CmdState.DoApogeeDomeFlatCmd()

        self.updateCartridge(-1,'UNKNOWN','None')
        sopState.guiderState.setLoadedNewCartridgeCallback(self.updateCartridge)

    def updateCartridge(self, cartridge, plateType, surveyModeName, status=True, bypassed=False):
        """
        Read the guider's notion of the loaded cartridge and configure ourselves appropriately.

        Args:
            cartridge (int): Cartridge ID number
            plateType (str): plateType keyword from the guider, used as a lookup into survey_dict
            surveyModeName (str): surveyMode keyword from the guider, used as a lookup into surveyMode_dict

        Kwargs:
            status (bool): Output status when done?
            bypassed (bool): Were we set via a bypass? If not, clear cart bypasses before doing anything else.
        """

        # clear cart bypasses on load cartridge, per #2284
        if not bypassed:
            myGlobals.bypass.clear_cart_bypasses()

        sopState = myGlobals.actorState
        cmd = sopState.actor.bcast

        sopState.cartridge = cartridge
        # save these for when someone sets a bypass.
        sopState.plateType = plateType
        sopState.surveyModeName = surveyModeName
        self.classifyCartridge(cmd, cartridge, plateType, surveyModeName)
        surveyMode = sopState.surveyMode
        survey = sopState.survey

        cmd.warn('text="loadCartridge fired cart=%s survey=%s surveyMode=%s"' % (cartridge, survey, surveyMode))
        cmd.inform("survey={0},{1}".format(*[qstr(x) for x in sopState.surveyText]))

        sopState.validCommands = ['gotoField',
                                  'gotoStow', 'gotoInstrumentChange', 'gotoAll60', 'gotoStow60']
        if survey is sopActor.BOSS:
            sopState.gotoField.setStages(['slew', 'hartmann', 'calibs', 'guider', 'cleanup'])
            sopState.validCommands += ['doBossCalibs', 'doBossScience',]
        elif survey is sopActor.APOGEE or survey is sopActor.APOGEE2S:
            apogeeDesign = self.update_apogee_design(sopState)
            sopState.doApogeeScience.set_apogee_expTime(apogeeDesign[1])
            if survey is sopActor.APOGEE2S:
                sopState.gotoField.setStages(['slew', 'screen', 'flat', 'darks',
                                              'guiderFlat', 'guider', 'cleanup'],
                                             setStagesTo='off')
            else:
                sopState.gotoField.setStages(['slew', 'guider', 'cleanup'])
            sopState.validCommands += ['doApogeeScience', 'doApogeeSkyFlats',
                                      'gotoGangChange', 'doApogeeDomeFlat']
        elif survey is sopActor.MANGA:
            sopState.gotoField.setStages(['slew', 'hartmann', 'calibs', 'guider', 'cleanup'])
            sopState.validCommands += ['doBossCalibs',
                                      'doMangaDither','doMangaSequence',]
            if surveyMode is sopActor.MANGADITHER:
                sopState.doMangaSequence.set_mangaDither()
            if surveyMode is sopActor.MANGASTARE:
                sopState.doMangaSequence.set_mangaStare()
        elif survey is sopActor.APOGEEMANGA:
            sopState.gotoField.setStages(['slew', 'hartmann', 'calibs', 'guider', 'cleanup'])
            sopState.validCommands += ['doBossCalibs',
                                      'doApogeeMangaDither','doApogeeMangaSequence',
                                      'doApogeeSkyFlats', 'gotoGangChange', 'doApogeeDomeFlat']
            if surveyMode is sopActor.APOGEELEAD:
                apogeeDesign = self.update_apogee_design(sopState)
                sopState.doApogeeMangaDither.set_apogeeLead(
                    apogeeExpTime=apogeeDesign[1])
                sopState.doApogeeMangaSequence.set_apogeeLead(
                    apogeeExpTime=apogeeDesign[1])
            if surveyMode is sopActor.MANGADITHER:
                sopState.doApogeeMangaDither.set_manga()
                sopState.doApogeeMangaSequence.set_mangaDither()
            if surveyMode is sopActor.MANGASTARE:
                sopState.doApogeeMangaDither.set_manga()
                sopState.doApogeeMangaSequence.set_mangaStare()
        else:
            sopState.gotoField.setStages(['slew', 'guider', 'cleanup'])

        if status:
            self.status(cmd, threads=False, finish=False)

    def update_apogee_design(self,sopState):
        """Update the APOGEE design parameters, including expTime, from the platedb keyword."""

        return sopState.models['platedb'].keyVarDict['apogeeDesign']

    def update_plugged_instruments(self,sopState):
        ''' Update the plugged instrument from the platedb keyword '''
        pluggedInstruments = sopState.models['platedb'].keyVarDict['pluggedInstruments']
        sopState.pluggedInstruments = pluggedInstruments.getValue()

    def survey_bypasses(self, cmd, sopState):
        """Set survey/surveyMode if a bypass is set and return True if so."""

        bypass = myGlobals.bypass
        sopState.survey = None
        sopState.surveyMode = None

        if bypass.get('isBoss'):
            cmd.warn('text="We are lying about this being a BOSS cartridge"')
            sopState.survey = sopActor.BOSS
            sopState.surveyMode = None
        elif bypass.get('isApogee'):
            cmd.warn('text="We are lying about this being an APOGEE cartridge"')
            sopState.survey = sopActor.APOGEE
            sopState.surveyMode = None
        elif bypass.get('isMangaStare'):
            cmd.warn('text="We are lying about this being a MaNGA Stare cartridge"')
            sopState.survey = sopActor.MANGA
            sopState.surveyMode = sopActor.MANGASTARE
        elif bypass.get('isMangaDither'):
            cmd.warn('text="We are lying about this being a MaNGA Dither cartridge"')
            sopState.survey = sopActor.MANGA
            sopState.surveyMode = sopActor.MANGADITHER
        elif bypass.get('isApogeeMangaStare'):
            cmd.warn('text="We are lying about this being an APOGEE&MaNGA Stare cartridge"')
            sopState.survey = sopActor.APOGEEMANGA
            sopState.surveyMode = sopActor.MANGASTARE
        elif bypass.get('isApogeeMangaDither'):
            cmd.warn('text="We are lying about this being a APOGEE&MaNGA Dither cartridge"')
            sopState.survey = sopActor.APOGEEMANGA
            sopState.surveyMode = sopActor.MANGADITHER
        elif bypass.get('isApogeeLead'):
            cmd.warn('text="We are lying about this being an APOGEE&MaNGA, APOGEE Lead cartridge"')
            sopState.survey = sopActor.APOGEEMANGA
            sopState.surveyMode = sopActor.APOGEELEAD

        return sopState.survey is not None

    def classifyCartridge(self, cmd, cartridge, plateType, surveyMode):
        """
        Set the survey and surveyMode for this cartridge in actorState.

        Args:
            cmd (Cmdr): Cmdr to send output to.
            cartridge (int): Cartridge ID number
            plateType (str): plateType keyword from the guider, used as a lookup into survey_dict
            surveyModeName (str): surveyMode keyword from the guider, used as a lookup into surveyMode_dict
        """
        def update_surveyText():
            sopState.surveyText = [survey_inv_dict[sopState.survey],
                                   surveyMode_inv_dict[sopState.surveyMode]]

        sopState = myGlobals.actorState
        sopState.surveyText = ['','']

        if self.survey_bypasses(cmd, sopState):
            update_surveyText()
            return

        if cartridge <= 0:
            cmd.warn('text="We do not have a valid cartridge (id=%s)"' % (cartridge))
            sopState.survey = sopActor.UNKNOWN
            sopState.surveyMode = None
            update_surveyText()
            return

        # NOTE: don't use .get() here to send an error message if the key lookup fails.
        # Set surveyText explicitly to exactly match the guider output.
        try:
            sopState.survey = survey_dict[plateType]
            sopState.surveyText[0] = plateType
        except KeyError:
            cmd.error('text=%s'%qstr("Do not understand plateType: %s."%plateType))
            sopState.survey = sopActor.UNKNOWN
            sopState.surveyText[0] = survey_inv_dict[sopState.survey]

        try:
            sopState.surveyMode = surveyMode_dict[surveyMode]
            sopState.surveyText[1] = surveyMode
        except KeyError:
            cmd.error('text=%s'%qstr("Do not understand surveyMode: %s."%surveyMode))
            sopState.surveyMode = None
            sopState.surveyText[1] = surveyMode_inv_dict[sopState.surveyMode]

        # #2453 Check which instruments were plugged for APOGEE-MaNGA plates
        self.update_plugged_instruments(sopState)
        if sopState.survey == sopActor.APOGEEMANGA:
            if sopState.pluggedInstruments == ('APOGEE',):
                sopState.survey = sopActor.APOGEE
                sopState.surveyMode = None
                update_surveyText()
            elif sopState.pluggedInstruments == ('BOSS',):
                sopState.survey = sopActor.MANGA
                sopState.surveyMode = sopActor.MANGADITHER
                update_surveyText()
            elif not sopState.pluggedInstruments:
                sopState.survey = sopActor.UNKNOWN
                sopState.surveyMode = None
                update_surveyText()

    def doing_science(self,sopState):
        """Return True if any sort of science command is currently running."""
        return (sopState.doBossScience.cmd and sopState.doBossScience.cmd.isAlive()) or \
               (sopState.doApogeeScience.cmd and sopState.doApogeeScience.cmd.isAlive()) or \
               (sopState.doMangaDither.cmd and sopState.doMangaDither.cmd.isAlive()) or \
               (sopState.doMangaSequence.cmd and sopState.doMangaSequence.cmd.isAlive()) or \
               (sopState.doApogeeMangaDither.cmd and sopState.doApogeeMangaDither.cmd.isAlive()) or \
               (sopState.doApogeeMangaSequence.cmd and sopState.doApogeeMangaSequence.cmd.isAlive())


def obs2Sky(cmd, az=None, alt=None, rotOffset=0.0):
    """Return ra, dec, rot for the current telescope position, for fake slews."""

    tccDict = myGlobals.actorState.models['tcc'].keyVarDict
    axePos = tccDict['axePos']
    gotoAz = az if az != None else axePos[0]
    gotoAlt = alt if alt != None else axePos[1]

    cmd.warn('text="FAKING slew position from az, alt, and rotator offset: %0.1f %0.1f %0.1f"'
             % (gotoAz, gotoAlt, rotOffset))
    cmdVar = myGlobals.actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd,
                                                  cmdStr=("convert %0.5f,%0.6f obs icrs" %
                                                          (gotoAz, gotoAlt)))
    if cmdVar.didFail:
        return 0,0,0
    else:
        convPos = tccDict['convPos']
        convAng = tccDict['convAng']

        rotPos = 180.0-convAng[0].getPos()
        rotPos += rotOffset

        # I think I need to do _something with the axePos rotation angle.
        return convPos[0].getPos(), convPos[1].getPos(), rotPos
