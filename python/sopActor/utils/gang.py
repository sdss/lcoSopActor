import sopActor.myGlobals as myGlobals


class ApogeeGang(object):
    """ Encapsulate the APOGEE gang connector. """

    GANG_UNKNOWN = 'unknown gang position'
    GANG_DISCONNECTED = 'gang disconnected'
    GANG_ON_CARTRIDGE = 'gang on cartridge'
    GANG_ON_PODIUM = 'gang on podium (any)'
    GANG_AT_DENSE = 'gang on podium: dense port'
    GANG_AT_SPARSE = 'gang on podium: sparse port'
    GANG_AT_1M = 'gang on podium: 1m port'

    def __init__(self, location='APO'):
        self.location = location.upper()

    def getPhysicalPos(self):
        """
        Return the gang position as indicated by the MCP apogeeGang keyword

        The mcp puts out an Int described as an Enum, which we map.

        jkp NOTE: We should be able to do this using just the actorkeys enum values.
        Also, this whole logic would probably be well encapsulated by some @property
        decorators...
        """
        gangMap = {0: self.GANG_UNKNOWN,
                   1: self.GANG_DISCONNECTED,
                   2: self.GANG_ON_CARTRIDGE,
                   4: self.GANG_ON_PODIUM,
                   12: self.GANG_AT_DENSE,
                   20: self.GANG_AT_SPARSE,
                   36: self.GANG_AT_1M
                   }

        mcpModel = myGlobals.actorState.models['mcp']
        gangPos = mcpModel.keyVarDict['apogeeGang']
        if not gangPos.isCurrent:
            return self.GANG_UNKNOWN

        return gangMap[int(gangPos[0])]

    def getPos(self):
        """
        Return the position of the gang connector.
        If a bypass is set, return the appropriate fake position.
        """
        bcast = myGlobals.actorState.actor.bcast

        if myGlobals.bypass.get(name='gangToPodium'):
            bcast.warn('text="Lying about the APOGEE gang connector being on the podium"')
            return self.GANG_ON_PODIUM
        elif myGlobals.bypass.get(name='gangToCart'):
            bcast.warn('text="Lying about the APOGEE gang connector being on the cartridge"')
            return self.GANG_ON_CARTRIDGE
        else:
            return self.getPhysicalPos()

    def atPodium(self, sparseOK=False, one_mOK=False):
        """
        Return True if the gang connector is on the podium.
        If sparseOK is True also accept being connected to the sparse port.
        if one_mOK is True, also accept being connected to the 1m port.
        """
        pos = self.getPos()
        ok = (pos == self.GANG_ON_PODIUM) or (pos == self.GANG_AT_DENSE)
        if sparseOK:
            ok = ok or (pos == self.GANG_AT_SPARSE)
        if one_mOK:
            ok = ok or (pos == self.GANG_AT_1M)

        return ok

    def atCartridge(self):

        # LCOHACK: for now, if we are at LCO we assume the gang connection is always at the cart.

        if self.location == 'APO':
            return self.getPos() == self.GANG_ON_CARTRIDGE
        elif self.location == 'LCO':
            return True
        else:
            raise ValueError('location {0} not valid'.format(self.location))
