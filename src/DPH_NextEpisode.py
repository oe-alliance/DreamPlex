# -*- coding: utf-8 -*-
"""
Next episode prompt.

Towards the end of an episode a panel with a countdown appears in the bottom
right corner: pressing OK plays the next episode straight away, pressing EXIT
dismisses the prompt, and if nothing happens playback moves on when the
countdown expires.

The same dialog doubles as the "you might also like" carousel DP_Player shows
near the end of a standalone movie (no next playlist entry to offer there,
unlike a show) - LEFT/RIGHT browse suggestions (DP_Player calls updateTitle()
for that, without touching the countdown), OK plays whichever one is
highlighted, and there is no countdown by default (a suggestion, unlike a
real next episode, is not something the user already committed to).

The panel is a dialog of its own rather than a widget of the player skin:
DP_Player inherits InfoBarShowHide, which hides the whole Screen when the user
dismisses the infobar, and an inner widget would disappear along with it. A
separate dialog instead stays visible above the video for as long as the
prompt lasts, which is the expected behaviour.

Key handling stays in DP_Player: this dialog never takes the focus, it only
shows the text and the countdown.
"""
from __future__ import annotations

from enigma import eTimer

from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel

from .__common__ import printl2 as printl
from . import _  # _ is translation


class DPH_NextEpisode(Screen):

	# Fallback skin: if the active skin does not define DPS_NextEpisode the
	# dialog stays usable instead of breaking the player. Sized for the
	# carousel's poster+summary (see updateArt()) - for a plain next-episode
	# prompt (a show) that space is just left blank, rather than keeping two
	# separate skins/layouts for what is otherwise the same dialog.
	skin = """
		<screen name="DPS_NextEpisode" position="center,center" size="640,200" flags="wfNoBorder" backgroundColor="#40000000">
			<widget name="carouselPoster" position="15,15" size="120,170" alphatest="blend" transparent="1" />
			<widget name="nextEpisodeText" position="150,10" size="475,30" font="Regular;22" transparent="1" foregroundColor="#FF8C00" backgroundColor="#40000000" />
			<widget name="nextEpisodeTitle" position="150,42" size="475,26" font="Regular;20" transparent="1" foregroundColor="#ffffff" backgroundColor="#40000000" noWrap="1" />
			<widget name="carouselSummary" position="150,70" size="475,95" font="Regular;16" transparent="1" foregroundColor="#cccccc" backgroundColor="#40000000" />
			<widget name="nextEpisodeHint" position="150,170" size="475,25" font="Regular;16" transparent="1" foregroundColor="#cccccc" backgroundColor="#40000000" />
		</screen>
		"""

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		self.skinName = ["DPS_NextEpisode"]

		self["carouselPoster"] = Pixmap()
		self["nextEpisodeText"] = Label()
		self["nextEpisodeTitle"] = Label()
		self["carouselSummary"] = ScrollLabel()
		self["nextEpisodeHint"] = Label(_("OK: play now     EXIT: cancel"))
		self.defaultHint = _("OK: play now     EXIT: cancel")

		self.secondsLeft = 0
		self.onExpired = None
		self.label = _("Next episode in %d s")

		self.countdownTimer = eTimer()
		self.countdownTimer.callback.append(self._tick)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def startCountdown(self, seconds, title, onExpired, label=None, hint=None):
		"""Show the panel, with or without a countdown.

		onExpired is called exactly once, when the time runs out - unless
		seconds is 0/None, in which case there is no timer at all and the
		panel just stays up until the caller hides it (DP_Player's "you
		might also like" carousel: OK plays the highlighted suggestion,
		nothing happens on its own unless autoplay is turned on in
		settings). `label` is the countdown text template (must contain one
		%d for the seconds left) - defaults to the next-episode wording.
		`hint` overrides the bottom key-legend line (e.g. to mention
		LEFT/RIGHT for the carousel).
		"""
		printl("seconds: " + str(seconds), self, "D")

		self.secondsLeft = int(seconds or 0)
		self.onExpired = onExpired
		self.label = label or _("Next episode in %d s")

		self["nextEpisodeTitle"].setText(title or "")
		self["nextEpisodeHint"].setText(hint or self.defaultHint)
		# cleared here so a plain next-episode prompt does not show whatever
		# the carousel last displayed - updateArt() (called right after by
		# DP_Player for the carousel case) fills it back in
		self["carouselSummary"].setText("")
		self._clearPoster()

		self.countdownTimer.stop()
		if self.secondsLeft > 0:
			self._refreshLabel()
			self.countdownTimer.start(1000, False)
		else:
			self["nextEpisodeText"].setText("")

		self.show()

	#===========================================================================
	# Updates just the title/hint - used by the carousel's LEFT/RIGHT
	# browsing, which must not disturb a running countdown (or lack of one).
	#===========================================================================
	def updateTitle(self, title, hint=None):
		self["nextEpisodeTitle"].setText(title or "")
		if hint is not None:
			self["nextEpisodeHint"].setText(hint)

	#===========================================================================
	# Poster + a summary excerpt for the currently highlighted carousel
	# entry - DP_Player decodes the poster (a separate ePicLoad instance
	# from the one showing the movie currently playing) and passes the
	# resulting pointer in; this dialog only ever renders it.
	#===========================================================================
	def updateArt(self, posterPtr, summary):
		self["carouselSummary"].setText(summary or "")
		if posterPtr is not None:
			try:
				self["carouselPoster"].instance.setPixmap(posterPtr)
			except Exception as e:
				printl("could not set suggestion poster: " + str(e), self, "W")
		else:
			self._clearPoster()

	#===========================================================================
	# UP/DOWN while the carousel is up, when the summary does not fit the
	# widget - carouselSummary is a ScrollLabel precisely for this.
	#===========================================================================
	def scrollSummaryUp(self):
		self["carouselSummary"].pageUp()

	def scrollSummaryDown(self):
		self["carouselSummary"].pageDown()

	#===========================================================================
	#
	#===========================================================================
	def _clearPoster(self):
		try:
			self["carouselPoster"].instance.setPixmap(None)
		except Exception:
			pass

	#===========================================================================
	#
	#===========================================================================
	def stopCountdown(self):
		self.countdownTimer.stop()
		self.onExpired = None
		self.hide()

	#===========================================================================
	#
	#===========================================================================
	def _refreshLabel(self):
		self["nextEpisodeText"].setText(self.label % max(0, self.secondsLeft))

	#===========================================================================
	#
	#===========================================================================
	def _tick(self):
		self.secondsLeft -= 1

		if self.secondsLeft > 0:
			self._refreshLabel()
			return

		# the callback is cleared before being invoked, so that it cannot run
		# twice should the timer fire again
		callback, self.onExpired = self.onExpired, None
		self.countdownTimer.stop()
		self.hide()

		if callback is not None:
			printl("countdown expired", self, "D")
			callback()
