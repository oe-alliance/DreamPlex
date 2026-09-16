# -*- coding: utf-8 -*-
"""
Small "working, please wait" overlay for blocking operations that have no
real per-step progress to report (a couple of synchronous network calls,
not a long per-item loop - see DP_View.initiateRefresh()). Enigma2 does not
repaint the screen while Python is busy inside a plain function call, so
this is shown, given one tick via eTimer to actually reach the screen, and
only then does the caller run its blocking work and hide this again -
without that one-tick defer the message would never be seen at all.
"""
from __future__ import annotations

from Screens.Screen import Screen
from Components.Label import Label

from .__common__ import printl2 as printl


class DPH_BusyIndicator(Screen):

	# Fallback skin: if the active skin does not define DPS_BusyIndicator the
	# dialog stays usable instead of breaking the caller.
	skin = """
		<screen name="DPS_BusyIndicator" position="center,center" size="520,90" flags="wfNoBorder" backgroundColor="#60000000">
			<widget name="busyText" position="0,0" size="520,90" font="Regular;24" halign="center" valign="center" transparent="1" foregroundColor="#ffffff" backgroundColor="#60000000" />
		</screen>
		"""

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		self.skinName = ["DPS_BusyIndicator"]

		self["busyText"] = Label()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showBusy(self, text):
		printl("", self, "S")

		self["busyText"].setText(text or "")
		self.show()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def hideBusy(self):
		self.hide()
