#!/usr/bin/env python2
# encoding: utf-8


# Created by Brian Cherinka on 2016-06-09 14:28:43
# Licensed under a 3-clause BSD license.

# Revision History:
#     Initial Version: 2016-06-09 14:28:43 by Brian Cherinka
#     Last Modified On: 2016-06-09 14:28:43 by Brian


from __future__ import print_function, division, absolute_import

import sys
from sopActor import Msg, SopActor

# start a new SopActor
if __name__ == "__main__":

    location = None if len(sys.argv) == 1 else sys.argv[1]
    sop = SopActor.SopActor.newActor(location=location)

    sop.run(Msg=Msg)
