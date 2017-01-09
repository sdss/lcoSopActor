import Queue, threading
import time

from sopActor import Msg
import sopActor
import sopActor.myGlobals as myGlobals

print "Loading TCC thread"

def get_bad_axis_bits(tccModel, axes=('az','alt','rot'), mask=None):
    """
    Return the bad status bits for the requested axes.
    Default mask is axisBadStatusMask (bad bits only), or some other bitmask.
    """
    if mask is None:
        mask = tccModel.keyVarDict['axisBadStatusMask'][0]
    return [(tccModel.keyVarDict['%sStat'%axis][3] & mask) for axis in axes]

def check_stop_in(actorState, axes=('az','alt','rot')):
    """
    Return true if any stop bit is set in the <axis>Stat TCC keywords.
    The [az,alt,rot]Stat[3] bits show the exact status:
    http://www.apo.nmsu.edu/Telescopes/HardwareControllers/AxisControllers.html#25mStatusBits
    """
    try:
        tccModel = actorState.models['tcc']
        # 0x2000 is "stop button in"
        return any(get_bad_axis_bits(tccModel,axes=axes,mask=0x2000))
    except TypeError:
        # some axisStat is unknown (and thus None)
        return False

def axes_are_ok(actorState, axes=('az','alt','rot')):
    """
    No bad bits set in any axis status field.
    Also return False if the badStatusMask or [axis]Stat is None.
    """
    try:
        tccModel = actorState.models['tcc']
        return not any(get_bad_axis_bits(tccModel,axes=axes))
    except TypeError:
        # axisStat or axisBadStatusMask is unknown (and thus None)
        return False

def axes_are_clear(actorState, axes=('az','alt','rot')):
    """No bits set in any axis status field."""
    try:
        tccModel = actorState.models['tcc']
        return all((tccModel.keyVarDict['%sStat'%axis][3] == 0) for axis in axes)
    except TypeError:
        # some axisStat is unknown (and thus None)
        return False

def axes_state(axisCmdState, state, axes=('az','alt','rot')):
    """Return True if all axes are in the given state."""
    ax = {'az':0, 'alt':1, 'rot':2}
    return all(state in axisCmdState[ax[x]].lower() for x in axes)

def some_axes_state(axisCmdState, state, axes=('az','alt','rot')):
    """Return True if any axis is in the given state."""
    ax = {'az':0, 'alt':1, 'rot':2}
    return any(state in axisCmdState[ax[x]].lower() for x in axes)

def below_alt_limit(actorState):
    """Check if we are below the alt=18 limit that prevents init/motion in az."""
    return actorState.models['tcc'].keyVarDict['axePos'][1] < 18

def mcp_semaphore_ok(cmd, actorState):
    """
    Return the semaphore if the semaphore is ok to take: owned by the TCC or nobody
    Return False, and issue error messages if not.
    """

    # If tron+sop have been restarted and mcp hasn't issued the keyword, there
    # will be no list to get a value from.
    try:
        sem = actorState.models['mcp'].keyVarDict['semaphoreOwner'][0]
    except IndexError:
        cmdVar = actorState.actor.cmdr.call(actor="mcp", forUserCmd=cmd, cmdStr="sem.show")
        if cmdVar.didFail:
            cmd.error('text="Error: Cannot get mcp semaphore. Is the mcp alive?"')
            return False
        sem = actorState.models['mcp'].keyVarDict['semaphoreOwner'][0]

    if (sem != 'TCC:0:0') and (sem != '') and (sem != 'None') and (sem != None):
        cmd.error('text="Cannot axis init: Semaphore is owned by '+sem+'"')
        cmd.error('text="If you are the owner (e.g., via MCP Menu), release it and try again."')
        cmd.error('text="If you are not the owner, confirm that you can steal it from them, then issue: mcp sem.steal"')
        return False

    return sem

def axis_init(cmd, actorState, replyQueue):
    """Send 'tcc axis init', and return status."""

    # need to send an axis status first, just to make sure the status bits have cleared
    cmdVar = actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd, cmdStr="axis status")
    # "tcc axis status" should never fail!
    if cmdVar.didFail:
        cmd.error('text="Cannot check axis status. Something is very wrong!"')
        cmd.error('text="Is the TCC in a responsive state?"')
        replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
        return

    # TBD: Another (cleaner?) solution would be to check the mcp
    # "sdssdc.status.i6.il0.*_stop" bits directly. See mcp/src/axis_cmds.c:check_stop_in()
    # for a list of the different stop bits.

    # if a stop button is in, we can't slew at all.
    if check_stop_in(actorState):
        # wait a couple seconds, then try again: the stop bits behave like sticky bits,
        # and may require two "tcc axis status" queries to fully clear.
        time.sleep(2)
        cmdVar = actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd, cmdStr="axis status")
        if check_stop_in(actorState):
            cmd.error('text="Cannot tcc axis init because of bad axis status: Check stop buttons on Interlocks panel."')
            replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
            return

    sem = mcp_semaphore_ok(cmd, actorState)
    if not sem:
        replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
        return

    if sem == 'TCC:0:0' and axes_are_clear(actorState):
        cmd.inform('text="Axes clear and TCC has semaphore. No axis init needed, so none sent."')
        replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
        return
    else:
        cmd.inform('text="Sending tcc axis init."')
        cmdStr = "axis init"
        if below_alt_limit(actorState):
            cmd.warn('text="Altitude below interlock limit! Only initializing altitude and rotator: cannot move in az."')
            cmdStr = ' '.join((cmdStr,"rot,alt"))
        cmdVar = actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd, cmdStr=cmdStr)

    if cmdVar.didFail:
        cmd.error('text="Cannot slew telescope: failed tcc axis init."')
        cmd.error('text="Cannot slew telescope: check and clear interlocks?"')
        replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
    else:
        replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
#...

def axis_stop(cmd, actorState, replyQueue):
    cmdVar = actorState.actor.cmdr.call(actor="tcc", forUserCmd=cmd, cmdStr="axis stop")
    if cmdVar.didFail:
        cmd.error('text="Error: failed to cleanly stop telescope via tcc axis stop."')
        replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
    else:
        replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
    return


class SlewHandler(object):
    """
    Handle slew commands, which can include a variety of separate arguments.
    Also remembers if the slew started below the alt limit, to still end cleanly.

    Example:
        slewHandler.parse_args(msg)
        slewHandler.do_slew(msg.cmd, msg.replyQueue)
    """
    def __init__(self, actorState, queue):
        self.actorState = actorState
        self.queue = queue
        self.reset()

    def reset(self):
        """Reset everything so we know the type of slew that is commanded."""
        self.alt, self.az = None, None
        self.ra, self.dec = None, None
        self.rot = None
        self.keepOffsets = False
        self.ignoreBadAz = False # for when we start below the alt limit.

    def parse_args(self, msg):
        """Extract the various potential arguments of a slew msg."""
        self.alt = getattr(msg, 'alt', None)
        self.az = getattr(msg, 'az', None)
        self.rot = getattr(msg, 'rot', None)
        self.ra = getattr(msg, 'ra', None)
        self.dec = getattr(msg, 'dec', None)
        self.keepOffsets = getattr(msg, 'keepOffsets', False)

    def slew(self, cmd, replyQueue):
        """Issue the commanded tcc track if the axes are ready to move."""

        # For LCO we don't do any check, just issue the slew.
        if self.actorState.actor.location.lower() == 'lco':
            self.do_slew_lco(cmd, replyQueue)
            return

        tccModel = self.actorState.models['tcc']
        # Fail before attempting slew if there's something wrong with an axis.
        if self.not_ok_to_slew(cmd):
            strAxisState = (','.join(tccModel.keyVarDict['axisCmdState']))
            strAxisCode = (','.join(tccModel.keyVarDict['axisErrCode']))
            axisBits = get_bad_axis_bits(tccModel, mask=0xffff)
            cmd.error('text="Trying to start slew with axis states: {}, error codes: {}, and status bits: 0x{:x},0x{:x},0x{:x}"'.format(strAxisState, strAxisCode, *axisBits))
            replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
            return

        self.do_slew(cmd, replyQueue)

    def axes_ok_with_bypass(self, axes=('az','alt','rot')):
        """Ignore the state of az when determing axis status."""
        return axes_are_ok(self.actorState,axes) or myGlobals.bypass.get(name='axes')

    def not_ok_to_slew(self, cmd):
        """Return True if we should not command a slew."""

        if self.ignoreBadAz:
            # If we were coming up from low alt, az will still be bad.
            return not self.axes_ok_with_bypass(('alt','rot'))
        if below_alt_limit(self.actorState):
            cmd.warn("text='Below alt=18 limit! Ignoring errors in Az, since we cannot move it anyway.'")
            self.ignoreBadAz = True
            return not self.axes_ok_with_bypass(('alt','rot'))
        else:
            return not self.axes_ok_with_bypass()

    def do_slew(self, cmd, replyQueue):
        """Correctly handle a slew command, given what parse_args had received."""
        call = self.actorState.actor.cmdr.call
        tccModel = self.actorState.models['tcc']

        # NOTE: TBD: We should limit which offsets are kept.
        keepArgs = "/keep=(obj,arc,gcorr,calib,bore)" if self.keepOffsets else ""

        if self.ra is not None and self.dec is not None:
            cmd.inform('text="slewing to ({:.4f}, {:.4f}, {:g})"'.format(self.ra, self.dec, self.rot))
            if keepArgs:
                cmd.warn('text="keeping all offsets"')
            cmdVar = call(actor="tcc", forUserCmd=cmd,
                          cmdStr="track %f, %f icrs /rottype=object/rotang=%g/rotwrap=mid %s" % \
                          (self.ra, self.dec, self.rot, keepArgs))
        else:
            cmd.inform('text="slewing to (az, alt, rot) == ({:.4f}, {:.4f}, {:.4f})"'.format(self.az, self.alt, self.rot))
            cmdVar = call(actor="tcc", forUserCmd=cmd,
                          cmdStr="track %f, %f mount/rottype=mount/rotangle=%f" % \
                          (self.az, self.alt, self.rot))

        # "tcc track" in the new TCC is only Done successfully when all requested
        # axes are in the "tracking" state. All other conditions mean the command
        # failed, and the appropriate axisCmdState and axisErrCode will be set.
        # However, if an axis becomes bad during the slew, the TCC will try to
        # finish it anyway, so we need to explicitly check for bad bits.

        if cmdVar.didFail:
            strAxisState = (','.join(tccModel.keyVarDict['axisCmdState']))
            strAxisCode = (','.join(tccModel.keyVarDict['axisErrCode']))
            cmd.error('text="tcc track command failed with axis states: {} and error codes: {}"'.format(strAxisState, strAxisCode))
            cmd.error('text="Failed to complete slew: see TCC messages for details."')
            replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
            return

        if self.not_ok_to_slew(cmd):
            axisBits = get_bad_axis_bits(tccModel)
            cmd.error('text="tcc track command ended with some bad bits set: 0x{:x},0x{:x},0x{:x}"'.format(*axisBits))
            cmd.error('text="Failed to complete slew: see TCC messages for details."')
            replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
        else:
            replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
        return

    def do_slew_lco(self, cmd, replyQueue, screen=True):
        """Commands the TCC at LCO to slew."""

        call = self.actorState.actor.cmdr.call
        screenCmd = '/screen' if screen else ''

        if self.ra is not None and self.dec is not None:
            cmd.inform('text="slewing to ({0:.4f}, {1:.4f})"'
                       .format(self.ra, self.dec))
            cmdVar = call(actor='tcc', forUserCmd=cmd,
                          cmdStr=('target {0:f}, {1:f} icrs {2}'
                                  .format(self.ra, self.dec, screenCmd)))

        if cmdVar.didFail:
            # TODO: add LCO specific error messages here.
            cmd.error('text=\"Failed to complete slew: '
                      'see TCC messages for details.\"')
            replyQueue.put(Msg.REPLY, cmd=cmd, success=False)
            return

        replyQueue.put(Msg.REPLY, cmd=cmd, success=True)
        return


def main(actor, queues):
    """Main loop for TCC thread"""

    threadName = "tcc"
    actorState = myGlobals.actorState
    timeout = actorState.timeout
    slewHandler = SlewHandler(actorState, queues[sopActor.TCC])

    while True:
        try:
            msg = queues[sopActor.TCC].get(timeout=timeout)

            if msg.type == Msg.EXIT:
                if msg.cmd:
                    msg.cmd.inform("text=\"Exiting thread %s\"" % (threading.current_thread().name))

                return

            elif msg.type == Msg.AXIS_INIT:
                axis_init(msg.cmd, actorState, msg.replyQueue)

            elif msg.type == Msg.AXIS_STOP:
                axis_stop(msg.cmd, actorState, msg.replyQueue)

            elif msg.type == Msg.SLEW:
                slewHandler.reset()
                slewHandler.parse_args(msg)
                slewHandler.slew(msg.cmd, msg.replyQueue)

            elif msg.type == Msg.STATUS:
                msg.cmd.inform('text="%s thread"' % threadName)
                msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=True)
            else:
                msg.cmd.warn("Unknown message type %s" % msg.type)
        except Queue.Empty:
            actor.bcast.diag('text="%s alive"' % threadName)
        except Exception, e:
            sopActor.handle_bad_exception(actor, e, threadName, msg)
