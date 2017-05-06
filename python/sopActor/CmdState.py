"""
Hold state about running commands, e.g. 'running', 'done', 'failed', ...
Also hold keywords for those commands as we pass them around.
"""
from opscore.utility.qstr import qstr

import sopActor.myGlobals as myGlobals
import sopActor

def getDefaultArcTime(survey):
    """Get the default arc time for this survey"""
    if survey == sopActor.BOSS or survey == sopActor.MANGA or sopActor.APOGEEMANGA:
        return 4
    else:
        return 0

def getDefaultFlatTime(survey):
    """Get the default flat time for this survey"""
    if survey == sopActor.BOSS or survey == sopActor.MANGA or sopActor.APOGEEMANGA:
        return 25
    else:
        return 0

class CmdState(object):
    """
    A class that's intended to hold command state data.

    Specify the various sub-stages of the command to allow stage states to be
    output for each of those sub-stages.

    When creating a new CmdState subclass, specify keywords with their default values
    for uncomplicated things (e.g. exposure time), and set class variables and define
    getUserKeys to output more complicated things (e.g. nExposures done vs. requested).
    Be careful that your getUserKeys names don't clobber other keywords.
    """

    # NOTE: these values need to match the *State enum values in actorkeys/sop.py
    # which are also used by STUI to cause various things to happen.
    # In particular:
    #   off     : uncheck that checkbox (danger: this means it will remain
    #                                    unchecked until a user re-checks it!)
    #   failed  : mark with error color.
    #   aborted : mark with warning color
    #   starting, prepping, running : mark with running color.
    validStageStates = ('prepping', 'running', 'done', 'failed', 'aborted', 'pending', 'off', 'idle')

    def __init__(self, name, allStages, keywords={}, hiddenKeywords=()):
        """
        Specify keywords with their default values: these will both be output automatically
        when the state changes.
        """
        self.name = name
        self.cmd = None
        self.cmdState = "idle"
        self.stateText = "OK"
        self.aborted = False
        self.keywords = dict(keywords)
        self.hiddenKeywords = hiddenKeywords
        self.reset_keywords()
        self.reset_nonkeywords()

        self.setStages(allStages)

    def reset_keywords(self):
        """Reset all the keywords to their default values."""
        for k, v in self.keywords.iteritems():
            setattr(self, k, v)

    def reset_nonkeywords(self):
        """Reset all non-keyword values to their defaults."""
        self.index = 0

    def set(self, name, value):
        """Sets self.name == value. if Value is None, use the default value."""
        assert name in self.keywords, qstr("%s is not in keyword list: %s"%(name,str(self.keywords)))
        if value is not None:
            setattr(self,name,value)
        else:
            setattr(self,name,self.keywords[name])

    def _getCmd(self, cmd=None):
        """Return the best cmd handler available."""
        if cmd:
            return cmd
        if self.cmd:
            return self.cmd
        return myGlobals.actorState.actor.bcast

    def setStages(self, allStages, setStagesTo='idle'):
        """Set the list of stages that are applicable, and make them idle."""
        self.allStages = allStages
        self.stages = dict(zip(allStages, [setStagesTo] * len(allStages)))
        for key in self.stages:
            if key == 'cleanup':
                self.stages[key] = 'idle'
        self.activeStages = allStages

    def reinitialize(self,cmd=None,stages=None,output=True, setStagesTo='idle'):
        """Re-initialize this cmdState, keeping the stages list as is."""
        self.stateText="OK"
        self.aborted = False
        myGlobals.actorState.aborting = False
        self.reset_keywords()
        self.reset_nonkeywords()
        if cmd is not None:
            self.cmd = cmd
        if stages is not None:
            self.setStages(stages, setStagesTo=setStagesTo)
        else:
            self.setStages(self.allStages, setStagesTo=setStagesTo)
        if output:
            self.genCommandKeys()

    def setupCommand(self, cmd, activeStages=[], name=''):
        """
        Setup the command for use, clearing stageStates, assigning new active stages,
        and outputting the currently-valid commandkeys and states.
        """
        if name:
            self.name = name
        self.cmd = cmd
        self.stateText="OK"
        self.activeStages = activeStages
        for name in self.allStages:
            self.setStageState(name, "pending" if name in activeStages else "off", genKeys=False)
        self.genCommandKeys()

    def setCommandState(self, state, genKeys=True, stateText=None):
        self.cmdState = state
        if stateText:
            self.stateText=stateText

        if genKeys:
            self.genKeys()

    def setStageState(self, name, stageState, genKeys=True):
        """Set a stage to a new state, and output the stage state keys."""
        assert name in self.stages, "stage %s is unknown, out of %s"%(name,repr(self.stages))
        assert stageState in self.validStageStates, "state %s is unknown, out of %s" % (stageState,repr(self.validStageStates))
        self.stages[name] = stageState

        if genKeys:
            self.genCmdStateKeys()

    def genCmdStateKeys(self, cmd=None):
        cmd = self._getCmd(cmd)
        cmd.inform("%sState=%s,%s,%s" % (self.name, qstr(self.cmdState),
                                         qstr(self.stateText),
                                         ",".join([qstr(self.stages[sname]) \
                                                       for sname in self.allStages])))

    def genCommandKeys(self, cmd=None):
        """ Return a list of the keywords describing our command. """

        cmd = self._getCmd(cmd)
        cmd.inform("%sStages=%s" % (self.name,
                                    ",".join([qstr(sname) \
                                                  for sname in self.allStages])))
        self.genCmdStateKeys(cmd=cmd)

    def getUserKeys(self):
        return []

    def genStateKeys(self, cmd=None):
        '''
        Generates command info statements for commmand keys
        Format: [commandName]_keyword = currentset_value, default_value
        e.g.
        doMangaSequence_count=1,3; doMangaSequence_dithers="NSE","NSE"
        doMangaSequence_expTime=900.0,900.0; doMangaSequence_ditherSeq=NSE,0
        '''
        cmd = self._getCmd(cmd)

        msg = []
        for keyName, default in self.keywords.iteritems():
            val = getattr(self, keyName)
            if type(default) == str:
                val = qstr(val)
                default = qstr(default)
            msg.append("%s_%s=%s,%s" % (self.name, keyName,
                                        val, default))
        if msg:
            cmd.inform("; ".join(msg))

        try:
            userKeys = self.getUserKeys()
        except:
            userKeys = []
            cmd.warn('text="failed to fetch all keywords for %s"' % (self.name))

        if userKeys:
            cmd.inform(";".join(userKeys))

    def genKeys(self, cmd=None, trimKeys=False):
        """Output all our keywords."""
        if not trimKeys or trimKeys == self.name:
            # [commandName]Stages and [commandName]State info statements (e.g. doMangaSequenceStages, doMangaSequenceState)
            self.genCommandKeys(cmd=cmd)
            # invidual state keys
            self.genStateKeys(cmd=cmd)

    def took_exposure(self):
        """Update keys after an exposure and output them."""
        self.index += 1
        self.genKeys()

    def isSlewingDisabled_BOSS(self):
        """Return False if the BOSS state is safe to start a slew."""
        safe_state = ('READING', 'IDLE', 'DONE', 'ABORTED')
        boss_state = myGlobals.actorState.models["boss"].keyVarDict["exposureState"][0]
        text = "; BOSS_exposureState=%s"%boss_state
        if boss_state not in safe_state:
            return True, text
        else:
            return False, text

    def isSlewingDisabled_APOGEE(self):
        """Returns False if the APOGEE state is safe to start a slew."""

        safe_state = ('DONE', 'STOPPED', 'FAILED')

        apogee_state = (myGlobals.actorState.models['apogee']
                        .keyVarDict['exposureState'][0])

        apogee_status_text = '; APOGEE_exposureState={0}'.format(apogee_state)

        if apogee_state.upper() not in safe_state:
            return True, apogee_status_text
        else:
            return False, apogee_status_text

    def abort(self):
        """Abort this command by clearing relevant variables."""
        self.aborted = True
        myGlobals.actorState.aborting = True
        self.abortStages()

    def abortStages(self):
        """ Mark all unstarted stages as aborted. """
        for s in self.activeStages:
            if not self.stages[s] in ("done", "failed", "off"):
                self.stages[s] = "aborted"
        self.genCmdStateKeys()

    def stop_boss_exposure(self):
        """Abort any currently running BOSS exposure, or warn if there's nothing to abort."""
        cmd = self._getCmd()
        # The same states we cannot slew during are the states we can't abort from.
        if self.isSlewingDisabled_BOSS()[0]:
            cmd.warn('text="Will cancel pending BOSS exposures and stop any running one."')
            call = myGlobals.actorState.actor.cmdr.call
            cmdVar = call(actor="boss", forUserCmd=cmd, cmdStr="exposure stop")
            if cmdVar.didFail:
                cmd.warn('text="Failed to stop running BOSS exposure"')
        else:
            cmd.warn('text="No BOSS exposure to abort!"')

    def stop_apogee_exposure(self):
        """Abort any currently running APOGEE exposure."""
        cmd = self._getCmd()
        cmd.warn('text="Will cancel pending APOGEE exposures and stop any running one."')
        call = myGlobals.actorState.actor.cmdr.call
        cmdVar = call(actor="apogee", forUserCmd=cmd, cmdStr="expose stop")
        if cmdVar.didFail:
            cmd.warn('text="Failed to stop running APOGEE exposure"')

    def stop_tcc(self):
        """Stop current TCC motion."""
        cmd = self._getCmd()
        cmdVar = myGlobals.actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd, cmdStr="axis stop")
        if cmdVar.didFail:
            cmd.warn('text="Failed to abort slew"')


#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

# Now define the actual command states we'll be using:

class GotoGangChangeCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'gotoGangChange',
                          ['domeFlat', 'slew'],
                          keywords=dict(alt=45.0))
        self.expType = "object"

    def reset_nonkeywords(self):
        self.doDomeFlat = True
        self.doSlew = True

    def abort(self):
        self.stop_apogee_exposure()
        self.stop_tcc()
        self.doDomeFlat = False
        self.doSlew = False
        super(GotoGangChangeCmd,self).abort()


class GotoPositionCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'gotoPosition', ['slew'],
                          keywords=dict(alt=30, az=121, rot=0))

    def reset_nonkeywords(self):
        self.doSlew = True

    def abort(self):
        self.stop_tcc()
        self.doSlew = False
        super(GotoPositionCmd, self).abort()


class DoApogeeDomeFlatCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doApogeeDomeFlat',
                          ['domeFlat'],
                          keywords=dict(expTime=50.0))
        self.expType = "object"

    def abort(self):
        self.stop_apogee_exposure()
        super(DoApogeeDomeFlatCmd,self).abort()


class HartmannCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'hartmann',
                          ['left','right','cleanup'],
                          keywords=dict(expTime=4))


class CollimateBossCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'collimateBoss',
                          ['collimate', 'cleanup'])


class GotoFieldCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'gotoField',
                          ['slew', 'hartmann', 'calibs', 'guider', 'cleanup'],
                          keywords=dict(arcTime=4,
                                        flatTime=25,
                                        guiderTime=5.0,
                                        guiderFlatTime=0.5))

    def reset_nonkeywords(self):
        self.fakeAz = None
        self.fakeAlt = None
        self.fakeRotOffset = 0.0
        self.ra = 0
        self.dec = 0
        self.rotang = 0
        self.keepOffsets = None
        self.doSlew = True
        self.doHartmann = True
        self.onlySlew = True
        self.ffScreen = True
        self.doCalibs = True
        self.didArc = False
        self.didFlat = False
        self.doGuiderFlat = True
        self.doGuider = True

    def abort(self):
        self.stop_boss_exposure()
        self.stop_tcc()
        self.doSlew = False
        self.ffScreen = False
        self.doHartmann = False
        self.doCalibs = False
        self.doGuiderFlat = False
        self.doGuider = False
        super(GotoFieldCmd,self).abort()


class GotoFieldLCOCmd(CmdState):

    def __init__(self):
        CmdState.__init__(self, 'gotoField',
                          ['slew', 'screen', 'flat', 'darks', 'guiderFlat', 'guider', 'cleanup'],
                          keywords=dict(flatTime=25,
                                        guiderTime=5.0,
                                        guiderFlatTime=20,
                                        nDarks=2,
                                        nDarkReads=10))

    def reset_nonkeywords(self):

        self.fakeAz = None
        self.fakeAlt = None
        self.fakeRotOffset = 0.0
        self.ra = 0
        self.dec = 0
        self.rotang = 0
        self.keepOffsets = None

        self.doSlew = True
        self.doScreen = True
        self.doGuiderFlat = True
        self.doGuider = True
        self.doFlat = True
        self.doDarks = True

    def abort(self):

        # self.stop_tcc()

        self.doSlew = False
        self.doScreen = False
        self.doGuiderFlat = False
        self.doGuider = False
        self.doFlat = False
        self.doDarks = False

        super(GotoFieldLCOCmd, self).abort()

    def reinitialize(self, setStagesTo='off', **kwargs):
        """Reinitialises all but sets stages to off."""

        super(GotoFieldLCOCmd, self).reinitialize(setStagesTo=setStagesTo, **kwargs)


class DoBossCalibsCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doBossCalibs',
                          ['bias', 'dark', 'flat', 'arc', 'cleanup'],
                          keywords=dict(darkTime=900.0,
                                        flatTime=25.0,
                                        arcTime=4.0,
                                        guiderFlatTime=0.5))

    def reset_nonkeywords(self):
        self.nBias = 0; self.nBiasDone = 0;
        self.nDark = 0; self.nDarkDone = 0;
        self.nFlat = 0; self.nFlatDone = 0;
        self.nArc = 0; self.nArcDone = 0;

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.nBiasDone < self.nBias or self.nDarkDone < self.nDark or \
                   self.nFlatDone < self.nFlat or self.nArcDone < self.nArc

    def getUserKeys(self):
        msg = []
        msg.append("nBias=%d,%d" % (self.nBiasDone, self.nBias))
        msg.append("nDark=%d,%d" % (self.nDarkDone, self.nDark))
        msg.append("nFlat=%d,%d" % (self.nFlatDone, self.nFlat))
        msg.append("nArc=%d,%d" % (self.nArcDone, self.nArc))
        return ["%s_%s" % (self.name, m) for m in msg]

    def abort(self):
        self.stop_boss_exposure()
        self.nArc = self.nArcDone
        self.nBias = self.nBiasDone
        self.nDark = self.nDarkDone
        self.nFlat = self.nFlatDone
        super(DoBossCalibsCmd,self).abort()


class DoApogeeScienceCmd(CmdState):

    def __init__(self):
        CmdState.__init__(self, 'doApogeeScience',
                          ['expose'],
                          keywords=dict(ditherPairs=4,
                                        expTime=500,
                                        comment=""))

    def reset_nonkeywords(self):
        self.expType = "object"
        super(DoApogeeScienceCmd, self).reset_nonkeywords()

    def set_apogee_expTime(self, value):
        """Set the default expTime to the new value, or the base if None."""
        if value is None:
            self.keywords['expTime'] = 500.
            self.expTime = 500.
        else:
            self.keywords['expTime'] = value
            self.expTime = value

    def getUserKeys(self):
        msg = []
        msg.append('%s_index=%d,%d' % (self.name,self.index,self.ditherPairs))
        return msg

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.index < self.ditherPairs

    def isSlewingDisabled(self):
        """If slewing is disabled, return a string describing why, else False."""
        if self.cmd and self.cmd.isAlive():
            return 'slewing disallowed for APOGEE, blocked by active doApogeeScience sequence'
        else:
            return False

    def abort(self):
        self.ditherPairs = self.index
        self.stop_apogee_exposure()
        super(DoApogeeScienceCmd,self).abort()


class DoApogeeSkyFlatsCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doApogeeSkyFlats',
                          ['offset','expose'],
                          keywords=dict(ditherPairs=2,
                                        expTime=150.0))
        self.exposureSeq = "ABBA"

    def reset_nonkeywords(self):
        self.expType = "object"
        self.comment = "sky flat, offset 0.01 degree in RA"
        super(DoApogeeSkyFlatsCmd,self).reset_nonkeywords()

    def getUserKeys(self):
        msg = []
        msg.append('%s_index=%d,%d' % (self.name,self.index,self.ditherPairs))
        return msg

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.index < self.ditherPairs

    def isSlewingDisabled(self):
        """If slewing is disabled, return a string describing why, else False."""
        if self.cmd and self.cmd.isAlive():
            return 'slewing disallowed for APOGEE, blocked by active doApogeeSkyFlat sequence'
        else:
            return False

    def abort(self):
        self.ditherPairs = self.index
        self.stop_apogee_exposure()
        super(DoApogeeSkyFlatsCmd,self).abort()


class DoBossScienceCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doBossScience',
                          ['expose'],
                          keywords=dict(expTime=900.0))
        self.nExp = 0
        self.index = 0

    def getUserKeys(self):
        msg = []
        msg.append("%s_nExp=%d,%d" % (self.name, self.index, self.nExp))
        return msg

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.index < self.nExp

    def isSlewingDisabled(self):
        """If slewing is disabled, return a string describing why, else False."""
        exp_state,exp_text = self.isSlewingDisabled_BOSS()
        remaining = self.nExp-self.index
        text = "slewing disallowed for BOSS, with %d science exposures left%s" % (remaining,exp_text)
        if self.cmd and self.cmd.isAlive() and (exp_state or remaining > 1):
            return text
        else:
            return False

    def abort(self):
        self.stop_boss_exposure()
        self.nExp = self.index
        super(DoBossScienceCmd, self).abort()


class DoMangaSequenceCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doMangaSequence',
                          ['expose', 'calibs', 'dither'],
                          keywords=dict(expTime=900.0,
                                        dithers='NSE',
                                        count=3))
        self.reset_ditherSeq()

    def reset_nonkeywords(self):
        super(DoMangaSequenceCmd, self).reset_nonkeywords()

    def set_mangaDither(self):
        """Setup to use this for MaNGA dither observations."""
        self.keywords = dict(expTime=900.0,
                             dithers='NSE',
                             count=3)
        self.count = 3
        self.dithers = 'NSE'
        if not (self.cmd and self.cmd.isAlive()):
            self.reset_ditherSeq()

    def set_mangaStare(self):
        """Setup to use this for MaNGA Stare observations."""
        self.keywords = dict(expTime=900.0,
                             dithers='CCC',
                             count=1)
        self.count = 1
        self.dithers = 'CCC'
        if not (self.cmd and self.cmd.isAlive()):
            self.reset_ditherSeq()

    def reset_ditherSeq(self):
        """Reset dither sequence based on dithers and count."""
        self.ditherSeq = self.dithers*self.count

    def getUserKeys(self):
        msg = []
        msg.append("%s_ditherSeq=%s,%s" % (self.name, self.ditherSeq, self.index))
        return msg

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.index < len(self.ditherSeq)

    def remaining_exposures(self):
        ''' Return the number of remaining exposures '''
        return len(self.ditherSeq) - self.index

    def current_dither(self):
        ''' Gets the current dither '''
        try:
            return self.ditherSeq[self.index]
        except Exception as e:
            return None

    def hasStateChanged(self, oldstate):
        ''' Check if the new state is different than old state '''
        if type(oldstate) == dict:
            return {'count': self.count, 'dithers': self.dithers, 'ditherSeq': self.ditherSeq} != oldstate
        else:
            return self.__dict__ != oldstate.__dict__

    def isSlewingDisabled(self):
        if (self.cmd and self.cmd.isAlive()):
            return "slewing disallowed for MaNGA, with a sequence in progress."
        else:
            return False

    def abort(self):
        self.stop_boss_exposure()
        super(DoMangaSequenceCmd, self).abort()


class DoMangaDitherCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doMangaDither',
                          ['expose','dither'],
                          keywords=dict(expTime=900.0,
                                        dither='C'))

    def reset_nonkeywords(self):
        self.readout = True

    def isSlewingDisabled(self):
        """If slewing is disabled, return a string describing why, else False."""
        exp_state,exp_text = self.isSlewingDisabled_BOSS()
        if (self.cmd and self.cmd.isAlive() and exp_state):
            return "slewing disallowed for MaNGA, with 1 science exposures left%s"%exp_text
        else:
            return False

    def abort(self):
        self.stop_boss_exposure()
        super(DoMangaDitherCmd,self).abort()


class DoApogeeMangaDitherCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doApogeeMangaDither',
                          ['expose','dither'],
                          keywords=dict(mangaExpTime=900.0,
                                        apogeeExpTime=450.0,
                                        mangaDither='C',
                                        comment=''))

        self.apogee_long = False

    def reset_nonkeywords(self):
        self.readout = True

    def set_apogeeLead(self, apogeeExpTime=None):
        """Setup to use this for APOGEE lead observations."""
        self.keywords=dict(mangaDither='C',
                           comment='')

        self.mangaDither = 'C'
        self.mangaExpTime=900.0

        if apogeeExpTime is None or apogeeExpTime <= 500:
            self.apogee_long = False
            self.apogeeExpTime = 500.
            self.keywords['apogeeExpTime'] = 500.
        else:
            self.apogee_long = True
            self.apogeeExpTime = 1000.
            self.keywords['apogeeExpTime'] = 1000.

    def set_manga(self):
        """Setup to use this for MaNGA (stare or dither) observations."""
        self.keywords=dict(mangaDither='C',
                           comment='')
        self.mangaDither = 'C'
        self.mangaExpTime=900.0
        self.apogeeExpTime=450.0
        self.apogee_long = False

    def getUserKeys(self):
        msg = []
        msg.append("%s_expTime=%s,%s" % (self.name, self.mangaExpTime, self.apogeeExpTime))
        return msg

    def isSlewingDisabled(self):
        """If slewing is disabled, return a string describing why, else False."""
        boss_disabled, boss_text = self.isSlewingDisabled_BOSS()
        apogee_disabled, apogee_text = self.isSlewingDisabled_APOGEE()
        if ((self.cmd and self.cmd.isAlive()) and
                (boss_disabled or apogee_disabled)):
            return ('slewing disallowed for APOGEE&MaNGA, '
                    'with 1 science exposures left{0}{1}'.format(boss_text,
                                                                 apogee_text))
        else:
            return False

    def abort(self):
        self.stop_boss_exposure()
        self.stop_apogee_exposure()
        super(DoApogeeMangaDitherCmd,self).abort()


class DoApogeeMangaSequenceCmd(CmdState):
    def __init__(self):
        CmdState.__init__(self, 'doApogeeMangaSequence',
                          ['expose','calibs','dither'],
                          keywords=dict(mangaDithers='NSE',
                                        count=2,
                                        comment=''))
        self.mangaExpTime=0
        self.apogeeExpTime=0
        self.apogee_long = False
        self.reset_ditherSeq()

    def set_apogeeLead(self, apogeeExpTime=None):
        """Setup to use this for APOGEE lead observations."""
        self.keywords=dict(mangaDithers='CC',
                           count=2,
                           comment='')

        self.mangaDithers = 'CC'
        self.count = 2
        self.mangaExpTime=900.0

        if apogeeExpTime is None or apogeeExpTime <= 500:
            self.apogee_long = False
            self.apogeeExpTime = 500.
            self.keywords['apogeeExpTime'] = 500.
        else:
            self.apogee_long = True
            self.apogeeExpTime = 1000.
            self.keywords['apogeeExpTime'] = 1000.

        self.readout = True
        if not (self.cmd and self.cmd.isAlive()):
            self.reset_ditherSeq()

    def set_mangaDither(self):
        """Setup to use this for MaNGA dither observations."""
        self.keywords=dict(mangaDithers='NSE',
                           count=2,
                           comment='')
        self.count = 2
        self.mangaDithers = 'NSE'
        self.mangaExpTime=900.0
        self.apogeeExpTime=450.0
        self.readout = False
        self.apogee_long = False
        if not (self.cmd and self.cmd.isAlive()):
            self.reset_ditherSeq()

    def set_mangaStare(self):
        """Setup to use this for MaNGA stare observations."""
        self.keywords=dict(mangaDithers='CCC',
                           count=2,
                           comment='')
        self.count = 2
        self.mangaDithers = 'CCC'
        self.mangaExpTime=900.0
        self.apogeeExpTime=450.0
        self.readout = False
        self.apogee_long = False
        if not (self.cmd and self.cmd.isAlive()):
            self.reset_ditherSeq()

    def reset_nonkeywords(self):
        super(DoApogeeMangaSequenceCmd,self).reset_nonkeywords()
        self.reset_ditherSeq()

    def reset_ditherSeq(self):
        """Reset dither sequence based on dithers,count parameters."""
        self.mangaDitherSeq = self.mangaDithers*self.count
        # Note: Two APOGEE exposures are taken for each MaNGA exposure.

    def getUserKeys(self):
        msg = []
        msg.append("%s_ditherSeq=%s,%s" % (self.name, self.mangaDitherSeq, self.index))
        msg.append("%s_expTime=%s,%s" % (self.name, self.mangaExpTime, self.apogeeExpTime))
        return msg

    def exposures_remain(self):
        """Return True if there are any exposures left to be taken."""
        if self.aborted:
            return False
        else:
            return self.index < len(self.mangaDitherSeq)

    def took_exposure(self):
        """Update keys after an exposure and output them."""

        if self.apogee_long:
            self.index += 2
        else:
            self.index += 1

        self.genKeys()

    @property
    def nExposureRemain(self):
        """Returns the number of exposures remaining."""

        return len(self.mangaDitherSeq) - self.index

    def isSlewingDisabled(self):

        boss_disabled, boss_text = self.isSlewingDisabled_BOSS()
        apogee_disabled, apogee_text = self.isSlewingDisabled_APOGEE()

        midSequence = self.exposures_remain()

        if (self.cmd and self.cmd.isAlive() and
                (apogee_disabled or boss_disabled or midSequence)):
            return ('slewing disallowed for APOGEE&MaNGA, with a sequence in '
                    'progress{0}{1}; {2} exposure(s) remaining'
                    .format(boss_text, apogee_text, self.nExposureRemain))
        else:
            return False

    def abort(self):
        self.stop_boss_exposure()
        self.stop_apogee_exposure()
        super(DoApogeeMangaSequenceCmd,self).abort()
