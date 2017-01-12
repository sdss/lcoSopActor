#!/usr/bin/env python
# encoding: utf-8
#
# sopActor_main.py
#
# Created by José Sánchez-Gallego on 17 Jul 2016.


from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

import sys

import sopActor
from sopActor import Msg, SopActor

# Start a new actor
if __name__ == '__main__':

    location = None if len(sys.argv) == 1 else sys.argv[1]
    sop = SopActor.SopActor.newActor(location=location)

    # sopActor uses its own subclass of Queue.
    # We send it to actorcore.SDSSActor so that the threads can be initialised
    # using it.
    sop.run(Msg=Msg, queueClass=sopActor.Queue)
