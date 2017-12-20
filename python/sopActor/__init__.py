import Queue as _Queue
import threading
import re
import six

from opscore.utility.qstr import qstr
from opscore.utility.tback import tback

import CmdState
import bypass

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
#
# Survey names; use classes so that the unique IDs are automatically generated
#
try:
    APOGEE
except NameError:
    class APOGEE(): pass
    class APOGEE2S(): pass
    class BOSS(): pass
    class MANGA(): pass
    class MANGASTARE(): pass
    class MANGADITHER(): pass
    class APOGEELEAD(): pass
    class APOGEEMANGA(): pass
    class ECAMERA(): pass
    class UNKNOWN(): pass

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
#
# Queue names; use classes so that the unique IDs are automatically generated
#
try:
    MASTER
except NameError:
    class MASTER(): pass
    class FFS(): pass                       # Flat Field Screen
    class FF_LAMP(): pass                   # FF lamps
    class HGCD_LAMP(): pass                 # HgCd lamps
    class HARTMANN(): pass                  # Do a Hartmann sequence
    class NE_LAMP(): pass                   # Ne lamps
    class UV_LAMP(): pass                   # uv lamps
    class WHT_LAMP(): pass                  # WHT lamps
    class BOSS(): pass                      # command the Boss ICC
    class GCAMERA(): pass                   # command the gcamera ICC
    class GUIDER(): pass                    # command the guider
    class TCC(): pass                       # command the TCC
    class APOGEE_SCRIPT(): pass
    class SCRIPT(): pass
    class SLEW(): pass                      # Slew the telescope.

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

try:
    Msg
except NameError:
    class Msg(object):
        # Priorities
        CRITICAL = 0
        HIGH = 2
        MEDIUM = 4
        NORMAL = 6

        # Command types; use classes so that the unique IDs are automatically generated
        class DO_BOSS_CALIBS(): pass
        class DITHERED_FLAT(): pass
        class SINGLE_HARTMANN(): pass
        class HARTMANN(): pass
        class COLLIMATE_BOSS(): pass
        class DO_BOSS_SCIENCE(): pass
        class DO_APOGEE_EXPOSURES(): pass
        class DO_MANGA_DITHER(): pass
        class DO_MANGA_SEQUENCE(): pass
        class DO_APOGEEMANGA_DITHER(): pass
        class DO_APOGEEMANGA_SEQUENCE(): pass
        class DO_APOGEE_SKY_FLATS(): pass
        class DO_APOGEE_DOME_FLAT(): pass
        class MANGA_DITHER(): pass
        class GOTO_GANG_CHANGE(): pass
        class GOTO_POSITION(): pass
        class DONE(): pass
        class EXIT(): pass
        class ENABLE(): pass
        class FFS_MOVE(): pass
        class FFS_COMPLETE(): pass
        class GOTO_FIELD(): pass
        class START(): pass
        class LAMP_ON(): pass
        class LAMP_COMPLETE(): pass
        class STATUS(): pass
        class EXPOSE(): pass
        class EXPOSURE_FINISHED(): pass
        class REPLY(): pass
        class SLEW(): pass
        class AXIS_INIT(): pass
        class AXIS_STOP(): pass
        class WAIT_UNTIL(): pass
        class DITHER(): pass
        class APOGEE_DITHER_SET(): pass
        class DECENTER(): pass
        class POST_FLAT(): pass
        class APOGEE_SHUTTER(): pass            # control the internal APOGEE shutter
        class APOGEE_PARK_DARKS(): pass
        class NEW_SCRIPT(): pass
        class STOP_SCRIPT(): pass
        class SCRIPT_STEP(): pass
        class TWODARKS(): pass

        def __init__(self, type, cmd, **data):
            self.type = type
            self.cmd = cmd
            self.priority = Msg.NORMAL

            self.duration = 0           # how long this command is expected to take (may be overridden by data)
            #
            # convert data[] into attributes
            #
            for k, v in data.items():
                self.__setattr__(k, v)
            self.__data = data.keys()

        def __repr__(self):
            values = []
            for k in self.__data:
                values.append("%s : %s" % (k, self.__getattribute__(k)))

            return "%s, %s: {%s}" % (self.type.__name__, self.cmd, ", ".join(values))

        def __cmp__(self, rhs):
            """Used when sorting the messages in a priority queue"""
            return self.priority - rhs.priority

class Queue(_Queue.PriorityQueue):
    """A queue type that checks that the message is of the desired type"""

    Empty = _Queue.Empty

    def __init__(self, name, *args):
        _Queue.Queue.__init__(self, *args)
        self.name = name

        assert isinstance(self.name, six.string_types), 'Queue name must be a string.'

    def __str__(self):
        return self.name

    def put(self, arg0, *args, **kwds):
        """
        Put  messaage onto the queue, calling the superclass's put method
        Expects a Msg, otherwise tries to construct a Msg from its arguments
        """

        if isinstance(arg0, Msg):
            msg = arg0
        else:
            msg = Msg(arg0, *args, **kwds)

        msg.senderName = threading.current_thread().name
        msg.senderName0 =  re.sub(r"(-\d+)?$", "", msg.senderName)
        msg.senderQueue = self

        _Queue.Queue.put(self, msg)

    def flush(self):
        """flush the queue"""

        while True:
            try:
                msg = self.get(timeout=0)
            except Queue.Empty:
                return

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

def handle_bad_exception(actor, e, threadName, msg):
    """
    For each thread's "global" unexpected exception handler.
    Send error, dump stacktrace, try to reply with a failure.
    """
    errMsg = qstr("Unexpected exception %s: %s, in sop %s thread" % (type(e).__name__, e, threadName))
    actor.bcast.error('text=%s' % errMsg)
    tback(errMsg, e)
    try:
        msg.replyQueue.put(Msg.REPLY, cmd=msg.cmd, success=False)
    except Exception, e:
        pass


__all__ = ["MASTER", "Msg", "bypass", "CmdState"]

__version__ = '1.0.0dev'
