===========
lcoSopActor
===========

SOP is the "Spectrograph Operating Program". sopActor manages high-level user
commands for observing tasks like "gotoField", "doBossScience",
"gotoGangChange", etc., generally operated via the SOP panel in STUI.

Flowcharts that diagram how the commands work are available in the
``operations/general/documentation`` package, and should be updated when one of
the commands changes.

Configuation (e.g. hosts/ports/logging directories) are found in the ``etc/``
directory.

This is the fork for LCO.
