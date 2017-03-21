import Queue, threading

import sopActor
from sopActor import Msg, tback
import sopActor.myGlobals as myGlobals

from opscore.utility.qstr import qstr

from twisted.internet import reactor, defer

EXP_COUNTER = 0

def twistedSleep(secs):
    d = defer.deferred()
    reactor.callLater(secs, d.callback, None)
    return d

def checkFailure(cmd, replyQueue, cmdVar, failmsg, finish=True):
    """
    Test whether cmdVar has failed, and if so issue failmsg as a 'warn' level text.
    Returns True if cmdVar failed, False if not.
    Send a success=True REPLY, if finish is True and we cmdVar didn't fail.
    Always send success=False if it did fail.
    """
    if cmdVar.didFail:
        cmd.error('text=%s'%qstr(failmsg))
        replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
        return True
    else:
        if finish:
            replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
        return False
#...

def do_dither(cmd, actorState, dither):
    """Move the APOGEE dither position."""
    timeLim = 30.0  # seconds
    cmdVar = actorState.actor.cmdr.call(actor="apogee", forUserCmd=cmd,
                                        cmdStr=("dither namedpos=%s" % dither),
                                        keyVars=[], timeLim=timeLim)
    return cmdVar
#...

def do_shutter(cmd,actorState,position):
    """Move the APOGEE shutter position."""
    cmdVar = actorState.actor.cmdr.call(actor="apogee", forUserCmd=cmd,
                                        cmdStr="shutter %s" % (position),
                                        timeLim=20)
    return cmdVar
#...

def do_expose(cmd, actorState, expTime, dither, expType, comment, nreads=None):
    """Take an exposure, moving the dither position if requested (not None)."""

    # may not specify nreads and expTime, fail if this is the case
    if expTime is not None and nreads is not None:
        cmd.error("text=%s"%qstr("May not specify expTime AND nreads!"))
        return False

    if dither != None:
        cmdVar = do_dither(cmd, actorState, dither)
        if cmdVar.didFail:
            cmd.error('text=%s'%qstr("Failed to move APOGEE dither to %s position."%(dither)))
            return False

    if nreads is not None:
        expFlavor = "nreads=%i"%nreads
        # read is 10.8 seconds, round up and add overhead
        timeLim = 11 * nreads + 15.0
    else:
        expFlavor = "time=%0.1f"%expTime
        timeLim = expTime + 15.0 # seconds

    comment = "comment=%s" % qstr(comment) if comment else ""
    exposeCmdStr = "expose %s object=%s %s"%(expFlavor, expType, comment)

    cmdVar = actorState.actor.cmdr.call(actor="apogee", forUserCmd=cmd,
                                        cmdStr=exposeCmdStr,
                                        keyVars=[], timeLim=timeLim)
    success = not cmdVar.didFail

    if not success:
        cmd.error('text="failed to start %s exposure"' % (expType))
    else:
        cmd.inform('text="done with %s exposure"' % (expType))
    return success

def do_apogee_dither_set(cmd, actorState, expTime, dithers, expType, comment):
    """
    A set of exposures at multiple dither positions, moving the dither
    in between as needed.
    """
    for i,dither in enumerate(dithers):
        if actorState.aborting:
            cmd.warn('text="Primary command aborted: stopping APOGEE dither set."')
            return False
        currentDither = actorState.models['apogee'].keyVarDict["ditherPosition"][1]
        # Per ticket #1756, APOGEE now does not want dither move requests unless necessary
        if dither == currentDither:
            cmd.inform('text="APOGEE dither already at desired position %s: not commanding move."'%(currentDither))
            dither = None
        cmd.inform('apogeeDitherSet=%s,%d'%(dithers,i))
        success = do_expose(cmd, actorState, expTime, dither, expType, comment)
        if not success:
            return False
    cmd.inform('apogeeDitherSet=%s,%d'%(dithers,i+1))
    return True

class ApogeeCB(object):
    def __init__(self):
        self.cmd = myGlobals.actorState.actor.bcast
        self.reset()
        myGlobals.actorState.models['apogee'].keyVarDict["utrReadState"].addCallback(self.listenToReads, callNow=True)

    def shutdown(self):
        # Setting doRaise=False since we don't care if the callback function
        # has ceased to exist when the thread exits (which is the only time this is called).
        myGlobals.actorState.models['apogee'].keyVarDict["utrReadState"].removeCallback(self.listenToReads,doRaise=False)

    def listenToReads(self, key):
        try:
            state = key[1]
            n = key[2]
        except:
            state="gack"
            n=42

        if not self.cmd.isAlive():
            self.cmd = myGlobals.actorState.actor.bcast
        self.cmd.diag('text="utrReadState=%s,%s count=%s trigger=%s"' %
                      (state, n, self.count, self.triggerCount))

        if self.triggerCount < 0:
            return
        if str(state) != "Reading":
            return

        self.count += 1

        try:
            #if not self.cmd.isAlive():
            #    self.cmd = myGlobals.actorState.actor.bcast
            self.cmd.diag('text="utrReadState2=%s,%s count=%s trigger=%s"' %
                          (state, n, self.count, self.triggerCount))

            if self.count == self.triggerCount:
                self.reset()
                # time.sleep(1)
                self.cb()
        except Exception as e:
            self.cmd.warn('text="failed to call callback: %s"' % (e))
            tback("cb", e)

    def reset(self):
        self.count = 0
        self.triggerCount = -1

    def waitForNthRead(self, cmd, n, q, cb=None):
        self.reset()
        self.cmd = cmd
        self.triggerCount = n
        self.q = q

        self.cb = cb if cb else self.flashLamps

    def turnOffLamps(self):
        self.cmd.diag('text="calling ff_lamp.off"')
        replyQueue = sopActor.Queue("apogeeFlasher")
        myGlobals.actorState.queues[sopActor.FF_LAMP].put(Msg.LAMP_ON, cmd=self.cmd, on=False, replyQueue=replyQueue)
        self.cmd.diag('text="called ff_lamp.off"')

    def flashLamps(self):
        time2flash = 4.0       # seconds

        replyQueue = sopActor.Queue("apogeeFlasher")
        self.cmd.diag('text="calling ff_lamp.on"')
        # NOTE: calling with noWait, so we don't wait for the mcp to respond.
        # This prevents the problem where one lamp doesn't turn on within 4 seconds.
        myGlobals.actorState.queues[sopActor.FF_LAMP].put(Msg.LAMP_ON, cmd=self.cmd, on=True, replyQueue=replyQueue, noWait=True)

        self.cmd.diag('text="called ff_lamp.on"')
        self.cmd.diag('text="pausing..."')
        reactor.callLater(time2flash, self.turnOffLamps)

def main(actor, queues):
    """Main loop for APOGEE ICC thread"""
    global EXP_COUNTER
    threadName = "apogee"
    actorState = myGlobals.actorState
    timeout = actorState.timeout

    # Set up readout callback object:

    while True:
        try:
            msg = actorState.queues[sopActor.APOGEE].get(timeout=timeout)

            if msg.type == Msg.EXIT:
                if msg.cmd:
                    msg.cmd.inform("text=\"Exiting thread %s\"" % (threading.current_thread().name))
                return

            elif msg.type == Msg.DITHER:
                cmdVar = do_dither(msg.cmd, actorState, msg.dither)
                checkFailure(msg.cmd,msg.replyQueue,cmdVar,"Failed to move APOGEE dither to %s position."%(msg.dither))

            elif msg.type == Msg.APOGEE_SHUTTER:
                position = "open" if msg.open else "close"
                cmdVar = do_shutter(msg.cmd, actorState, position)
                checkFailure(msg.cmd,msg.replyQueue,cmdVar,"Failed to %s APOGEE internal shutter."%(position))

            elif msg.type == Msg.EXPOSE:
                dither = getattr(msg,'dither',None)
                expType = getattr(msg,'expType','dark')
                comment = getattr(msg,'comment','')
                nreads = getattr(msg, 'nreads', None)
                expTime = getattr(msg, "expTime", None)
                EXP_COUNTER += 1
                msg.cmd.warn("APOGEE Expose nreads=%i expType=%s expTime=%s expCounter=%i"%(nreads, expType, str(expTime), EXP_COUNTER))
                success = do_expose(msg.cmd, actorState, expTime, dither, expType, comment, nreads)
                msg.replyQueue.put(Msg.EXPOSURE_FINISHED, cmd=msg.cmd, success=success)

            elif msg.type == Msg.APOGEE_DITHER_SET:
                dithers = getattr(msg,'dithers','AB')
                expType = getattr(msg,'expType','object')
                comment = getattr(msg,'comment','')
                success = do_apogee_dither_set(msg.cmd, actorState, msg.expTime, dithers, expType, comment)

                msg.replyQueue.put(Msg.EXPOSURE_FINISHED, cmd=msg.cmd, success=success)

            elif msg.type == Msg.STATUS:
                msg.cmd.inform('text="%s thread"' % threadName)
                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
            else:
                raise ValueError, ("Unknown message type %s" % msg.type)
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
        except Queue.Empty:
            actor.bcast.diag('text="%s alive"' % threadName)
        except Exception as e:
            sopActor.handle_bad_exception(actor,e,threadName,msg)

def script_main(actor, queues):
    """Main loop for APOGEE scripting thread"""

    threadName = "apogeeScript"
    actorState = myGlobals.actorState
    timeout = actorState.timeout
    apogeeFlatCB = ApogeeCB()

    script = None

    # Set up readout callback object:

    while True:
        try:
            msg = actorState.queues[sopActor.APOGEE_SCRIPT].get(timeout=timeout)

            if msg.type == Msg.EXIT:
                if msg.cmd:
                    msg.cmd.inform("text=\"Exiting thread %s\"" % (threading.current_thread().name))
                apogeeFlatCB.shutdown()
                return

            elif msg.type == Msg.NEW_SCRIPT:
                if msg.script:
                    msg.cmd.warn('text="%s thread is already running a script: %s"' %
                             (threadName, script.name))
                    msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=False)
                msg.script = msg.script
                msg.script.genStartKeys()
                actorState.queues[sopActor.APOGEE_SCRIPT].put(Msg.SCRIPT_STEP, msg.cmd)

            elif msg.type == Msg.SCRIPT_STEP:
                pass

            elif msg.type == Msg.STOP_SCRIPT:
                if not msg.script:
                    msg.cmd.warn('text="%s thread is not running a script, so cannot stop it."' %
                             (threadName))
                    msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=False)

            elif msg.type == Msg.POST_FLAT:
                cmd = msg.cmd
                n = 3

                actorState.queues[sopActor.APOGEE].put(Msg.EXPOSE, cmd, replyQueue=msg.replyQueue,
                                                       expTime=50, expType='DomeFlat')
                apogeeFlatCB.waitForNthRead(cmd, n, msg.replyQueue)

            elif msg.type == Msg.APOGEE_PARK_DARKS:
                cmd = msg.cmd
                n = 2
                # expTime = 100.0

                if True:
                    cmd.warn('text="SKIPPING darks"')
                    success = True
                else:
                    success = True

                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=success)

            elif msg.type == Msg.EXPOSURE_FINISHED:
                msg.replyQueue.put(Msg.EXPOSURE_FINISHED, cmd=msg.cmd, success=msg.success)

            elif msg.type == Msg.STATUS:
                msg.cmd.inform('text="%s thread"' % threadName)
                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
            else:
                raise ValueError, ("Unknown message type %s" % msg.type)
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
        except Queue.Empty:
            actor.bcast.diag('text="%s alive"' % threadName)
        except Exception, e:
            sopActor.handle_bad_exception(actor,e,threadName,msg)
