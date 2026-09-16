# -*- coding: utf-8 -*-
"""
Playback info panel (INFO/Guide key).

A richer, on-demand overview of what is currently playing - poster, title,
plot and metadata (year, genre, rating, cast/director, duration) - shown for
a fixed number of seconds or until the user presses EXIT/cancel, whichever
comes first. This is deliberately a separate dialog from the plain OK-key
progress overlay (InfoBarShowHide's native toggleShow()): that one already
carries the poster/title/plot and is meant to be glanced at and dismissed
quickly, while this one is meant to be read.

Same reasoning as DPH_NextEpisode for being its own dialog rather than a
widget of the player skin: DP_Player inherits InfoBarShowHide, which hides
the whole Screen when the OSD is dismissed, and an inner widget would
disappear along with it.
"""
from __future__ import annotations

from enigma import eTimer

from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap

from .__common__ import printl2 as printl
from . import _  # _ is translation

DEFAULT_DISPLAY_SECONDS = 15


class DPH_PlaybackInfo(Screen):

	# Fallback skin: if the active skin does not define DPS_PlaybackInfo the
	# dialog stays usable instead of breaking the player.
	skin = """
		<screen name="DPS_PlaybackInfo" position="center,center" size="900,420" flags="wfNoBorder" backgroundColor="#40000000">
			<widget name="infoPoster" position="15,15" size="195,268" alphatest="blend" transparent="1" />
			<widget name="infoTitle" position="230,15" size="655,40" font="Regular;28" transparent="1" foregroundColor="#FF8C00" backgroundColor="#40000000" noWrap="1" />
			<widget name="infoMeta" position="230,60" size="655,30" font="Regular;18" transparent="1" foregroundColor="#cccccc" backgroundColor="#40000000" noWrap="1" />
			<widget name="infoSummary" position="230,100" size="655,290" font="Regular;20" transparent="1" foregroundColor="#ffffff" backgroundColor="#40000000" />
			<widget name="infoHint" position="15,390" size="870,25" font="Regular;16" transparent="1" foregroundColor="#cccccc" backgroundColor="#40000000" />
		</screen>
		"""

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		self.skinName = ["DPS_PlaybackInfo"]

		self["infoPoster"] = Pixmap()
		self["infoTitle"] = Label()
		self["infoMeta"] = Label()
		self["infoSummary"] = Label()
		self["infoHint"] = Label(_("EXIT: close"))

		self.dismissTimer = eTimer()
		self.dismissTimer.callback.append(self.hideInfo)

		# Set by DP_Player so it learns about an auto-dismiss (the display
		# timer below) the same way it learns about an explicit EXIT - see
		# DPH_RatingPanel.onDismiss for the same reasoning.
		self.onDismiss = None

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showInfo(self, title, summary, metaLine, posterPtr, displaySeconds=DEFAULT_DISPLAY_SECONDS):
		printl("", self, "S")

		self["infoTitle"].setText(title or "")
		self["infoMeta"].setText(metaLine or "")
		self["infoSummary"].setText(summary or "")

		if posterPtr is not None:
			try:
				self["infoPoster"].instance.setPixmap(posterPtr)
			except Exception as e:
				printl("could not set poster: " + str(e), self, "W")

		self.show()

		self.dismissTimer.stop()
		if displaySeconds:
			self.dismissTimer.start(int(displaySeconds) * 1000, True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def hideInfo(self):
		self.dismissTimer.stop()
		self.hide()
		if self.onDismiss is not None:
			self.onDismiss()
