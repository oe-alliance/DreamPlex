# -*- coding: utf-8 -*-
"""
FAV-key rating/favorite panel.

Jellyfin dropped the personal star rating Plex has - only a favorite
on/off flag survives in its current API - so this dialog shows one of two
different things depending on the active server, decided entirely by
DP_Player (this class only renders whatever it is told to):

- Jellyfin: a favorite toggle. "1" marks it, "0" unmarks it, OK submits.
- Plex: a 0-5 star rating (half-star steps). Digits 1-5 pick which star to
  fill up to, alternating half/full on repeated presses of the same digit,
  OK submits.

ESC/EXIT closes without submitting either way. Same reasoning as
DPH_NextEpisode/DPH_PlaybackInfo for being a separate dialog rather than a
widget of the player skin - InfoBarShowHide hides the whole Screen when the
OSD is dismissed, and an inner widget would disappear along with it. Key
handling stays in DP_Player; this dialog only renders text.
"""
from __future__ import annotations

from enigma import eTimer

from Screens.Screen import Screen
from Components.Label import Label

from .__common__ import printl2 as printl
from . import _  # _ is translation

DEFAULT_DISPLAY_SECONDS = 8


class DPH_RatingPanel(Screen):

	# Fallback skin: if the active skin does not define DPS_RatingPanel the
	# dialog stays usable instead of breaking the player.
	skin = """
		<screen name="DPS_RatingPanel" position="center,center" size="520,140" flags="wfNoBorder" backgroundColor="#40000000">
			<widget name="ratingTitle" position="15,10" size="490,30" font="Regular;22" transparent="1" foregroundColor="#FF8C00" backgroundColor="#40000000" halign="center" />
			<widget name="ratingValue" position="15,48" size="490,42" font="Regular;30" transparent="1" foregroundColor="#ffffff" backgroundColor="#40000000" halign="center" />
			<widget name="ratingHint" position="15,100" size="490,25" font="Regular;16" transparent="1" foregroundColor="#cccccc" backgroundColor="#40000000" halign="center" />
		</screen>
		"""

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		self.skinName = ["DPS_RatingPanel"]

		self["ratingTitle"] = Label()
		self["ratingValue"] = Label()
		self["ratingHint"] = Label()

		self.dismissTimer = eTimer()
		self.dismissTimer.callback.append(self.hideRating)

		# Set by DP_Player so it learns about an auto-dismiss (the 8s timer
		# below) the same way it learns about an explicit EXIT - otherwise it
		# keeps believing the panel is open and digits/EXIT/OK still act on
		# an overlay that has not been visible for a while.
		self.onDismiss = None

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showFavorite(self, isFavorite, displaySeconds=DEFAULT_DISPLAY_SECONDS):
		self["ratingTitle"].setText(_("Favorite"))
		self["ratingValue"].setText("♥" if isFavorite else "♡")
		self["ratingHint"].setText(_("1: mark   0/RED: unmark   OK: confirm   EXIT: cancel"))
		self._show(displaySeconds)

	#===========================================================================
	#
	#===========================================================================
	def showStars(self, rating0to10, cleared=False, displaySeconds=DEFAULT_DISPLAY_SECONDS):
		self["ratingTitle"].setText(_("Rating"))
		self["ratingValue"].setText(_("☆☆☆☆☆  (cleared)") if cleared else self._starsText(rating0to10))
		self["ratingHint"].setText(_("1-5: select stars   RED: clear   OK: confirm   EXIT: cancel"))
		self._show(displaySeconds)

	#===========================================================================
	#
	#===========================================================================
	def _starsText(self, rating0to10):
		if not rating0to10:
			return "☆☆☆☆☆  (0/5)"

		full = int(rating0to10) // 2
		half = int(rating0to10) % 2 == 1
		empty = max(0, 5 - full - (1 if half else 0))

		stars = ("★" * full) + ("½" if half else "") + ("☆" * empty)
		return "%s  (%.1f/5)" % (stars, rating0to10 / 2.0)

	#===========================================================================
	#
	#===========================================================================
	def _show(self, displaySeconds):
		self.show()

		self.dismissTimer.stop()
		if displaySeconds:
			self.dismissTimer.start(int(displaySeconds) * 1000, True)

	#===========================================================================
	#
	#===========================================================================
	def hideRating(self):
		self.dismissTimer.stop()
		self.hide()
		if self.onDismiss is not None:
			self.onDismiss()
