# -*- coding: utf-8 -*-
"""
DreamPlex Plugin by DonDavici, 2012
and jbleyel 2021

Original -> https://github.com/oe-alliance/DreamPlex
Fork -> https://github.com/oe-alliance/DreamPlex

Some of the code is from other plugins:
all credits to the coders :-)

DreamPlex Plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 2 of the License, or
(at your option) any later version.

DreamPlex Plugin is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
"""
#===============================================================================
# IMPORT
#===============================================================================

from os import remove
from time import sleep, localtime, time, strftime

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.MinuteInput import MinuteInput
from Screens.ChoiceBox import ChoiceBox
from Screens.HelpMenu import HelpableScreen
from Tools.ISO639 import LanguageCodes

#noinspection PyUnresolvedReferences
from enigma import eServiceReference, eConsoleAppContainer, iPlayableService, eTimer, eServiceCenter, iServiceInformation, ePicLoad, eDVBVolumecontrol

from Tools import Notifications
from Tools.Directories import fileExists

from Components.VolumeControl import VolumeControl
from Components.AVSwitch import AVSwitch
from Components.Pixmap import Pixmap
from Components.Label import Label
from Components.ActionMap import ActionMap, HelpableActionMap
from Components.Slider import Slider
from Components.Sources.StaticText import StaticText
from Components.Language import language
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase

from Screens.AudioSelection import AudioSelection
from Screens.InfoBarGenerics import InfoBarShowHide, \
	InfoBarSeek, InfoBarAudioSelection, \
	InfoBarServiceNotifications, InfoBarSimpleEventView, \
	InfoBarExtensions, InfoBarNotifications, \
	InfoBarSubtitleSupport, InfoBarServiceErrorPopupSupport, InfoBarCueSheetSupport, InfoBarMoviePlayerSummary
from . import SettingsStorage

from .DPH_Singleton import Singleton
#from .DP_Summary import DreamplexPlayerSummary
from .DPH_ScreenHelper import DPH_ScreenHelper
from .DPH_NextEpisode import DPH_NextEpisode
from .DPH_PlaybackInfo import DPH_PlaybackInfo
from .DPH_RatingPanel import DPH_RatingPanel
from .DP_MediaLibrary import RATING_KIND_NONE, RATING_KIND_FAVORITE, RATING_KIND_STARS

from .__common__ import printl2 as printl, convertSize, encodeThat
from . import _  # _ is translation


# we need this to see the states for subtitles also in audioselction with yellow button
SUBTITLES_ENABLED = False
SUBTITLES_CONTENT = None


#===============================================================================
#
#===============================================================================


class InfobarAudioSelectionExtended(InfoBarAudioSelection):
	def __init__(self):
		InfoBarAudioSelection.__init__(self)

	#===========================================================================
	#
	#===========================================================================
	def audioSelection(self):
		printl("mh: audioSelection", self, "D")
		self.session.openWithCallback(self.audioSelected, myAudioSelection, infobar=self.session.infobar or self)

#===============================================================================
#
#===============================================================================


class myAudioSelection(AudioSelection):
	def __init__(self, session, infobar=None):
		printl("mh: myAudioSelection.__init__: session=" + str(session) + ", infobar=" + str(infobar), self, "D")

		AudioSelection.__init__(self, session, infobar)
		self.skinName = ["AudioSelection"]

		# check if we are active and we have content
		if SUBTITLES_CONTENT and SUBTITLES_ENABLED:
			printl("mh: myAudioSelection.__init__ (2)", self, "D")

			# run to set subtitle active in screen
			self.enableSubtitle(SUBTITLES_CONTENT)

#===============================================================================
#
#===============================================================================


def _nextPlexStarRating(prevDigit, prevIsFull, digit):
	"""Pure logic behind the Plex star-rating panel's digit keys (1-5): each
	digit selects which star to fill up to, alternating half/full on
	repeated presses of that same digit; pressing a different digit always
	starts that new position at half. Returns (newDigit, newIsFull,
	newValue), where newValue is the resulting 0-10 rating (half-star
	steps). Kept standalone from DP_Player so it can be unit-tested without
	a live player instance.
	"""
	if prevDigit == digit:
		newIsFull = not prevIsFull
	else:
		newIsFull = False

	newValue = digit * 2 - (0 if newIsFull else 1)
	return digit, newIsFull, newValue


class DP_Player(Screen, InfoBarBase, InfoBarShowHide, InfoBarCueSheetSupport,
		InfoBarSeek, InfobarAudioSelectionExtended, HelpableScreen,
		InfoBarServiceNotifications, InfoBarSimpleEventView,
		InfoBarSubtitleSupport, InfoBarServiceErrorPopupSupport, InfoBarExtensions, InfoBarNotifications, DPH_ScreenHelper):

	ENIGMA_SERVICE_ID = None
	ENIGMA_SERVICETS_ID = 0x1		#1
	ENIGMA_SERVIDEM2_ID = 0x3		#3
	ENIGMA_SERVICEGS_ID = 0x1001  # 4097

	seek = None
	resume = False
	resumeStamp = 0
	server = None
	id = None
	url = None
	transcodingSession = None
	universalTranscoder = False
	transcoderHeartbeat = None
	videoData = None
	mediaData = None
	multiUser = False

	tagline = ""
	summary = ""
	year = ""
	studio = ""
	duration = ""
	contentRating = ""

	audioCodec = ""
	videoCodec = ""
	videoResolution = ""
	videoFrameRate = ""

	nTracks = False
	switchedLanguage = False
	timeshift_enabled = False
	isVisible = False
	playbackType = None
	timelineWatcher = None
	whatPoster = None
	subtitleStreams = None
	subtitleLanguageCode = None
	subtitleWatcher = None

	#mh
	mhSeekHack = 0

	#===========================================================================
	#
	#===========================================================================

	def __init__(self, session, listViewList, currentIndex, libraryName, autoPlayMode, resumeMode, playbackMode, forceResume=False, isExtraData=False, sessionData=None, subtitleData=None, startedByRemotePlayer=False, autoSelectFirstMedia=False):
		printl("", self, "S")
		Screen.__init__(self, session)

		if libraryName == "music":
			self.skinName = "DPS_MusicPlayer"
			self.calculateEndingTime = False
		else:
			self.skinName = "DPS_VideoPlayer"
			self.calculateEndingTime = True

		for x in HelpableScreen, InfoBarShowHide, InfoBarBase, InfoBarSeek, \
				InfobarAudioSelectionExtended, InfoBarSimpleEventView, \
				InfoBarServiceNotifications, InfoBarSubtitleSupport, \
				InfoBarServiceErrorPopupSupport, InfoBarExtensions, InfoBarNotifications:
			printl("x: " + str(x), self, "D")
			x.__init__(self)
		printl("currentIndex: " + str(currentIndex), self, "D")

		self.settings: SettingsStorage = Singleton().getSettingsInstance()

		self.listViewList = listViewList
		self.currentIndex = currentIndex
		self.listCount = len(self.listViewList) - 1  # list starts counting with 0
		self.playerData = {}
		self.autoPlayMode = autoPlayMode
		self.resumeMode = resumeMode
		self.forceResume = forceResume  # we use this to able to resume out of android or ios
		self.playbackMode = playbackMode
		self.isExtraData = isExtraData
		self.sessionData = sessionData
		self.subtitleData = subtitleData
		self.startedByRemotePlayer = startedByRemotePlayer
		# The Carousel hero's BLUE-key shortcut promises "play now" -
		# stopping at an unlabeled ChoiceBox for a multi-version item (see
		# selectMedia()) instead reads as "nothing happened": the poster/
		# title are already on screen from the constructor args below, the
		# ChoiceBox itself is easy to miss, and STOP from there abandons
		# playback entirely (see DP_ServerMenu._playHeroItem()). Set only by
		# that one caller - every other entry point keeps the picker.
		self.autoSelectFirstMedia = autoSelectFirstMedia
		self.onChangedEntry = []

		printl("mh: subtitleData=" + str(subtitleData), self, "D")

		# we add this for vix images due to their long press button support
		self.LongButtonPressed = False

		self.libraryName = libraryName

		self.plexInstance = Singleton().getMediaLibrary()

		self.initScreen(self.skinName)

		self.bufferslider = Slider(0, 100)
		self["bufferslider"] = self.bufferslider

		self.bufferSeconds = 0
		self.bufferPercent = 0
		self.bufferSecondsLeft = 0
		self.bitrate = 0
		self.endReached = False

		# HelpableActionMap (not plain ActionMap): descriptions below feed
		# the native Help-key legend. HelpMenu only lists an action if its
		# description is a non-empty string, so this is what makes these
		# bindings show up under Help at all - every other HelpableActionMap
		# in this codebase (DP_View, DP_MainMenu, ...) was left with all-""
		# descriptions and so contributes nothing to Help either.
		self["actions"] = HelpableActionMap(self, ["DPS_Player"],
		{
		# keymap.xml maps KEY_OK to "ok" within the "DPS_Player" context,
		# which shadows the system-wide "InfobarActions" context (KEY_OK ->
		# "toggleShow") that InfoBarShowHide's own ActionMap listens on - so
		# without a handler here OK does nothing at all, instead of falling
		# through to the native show/hide toggle. This map's priority (-2)
		# is higher than nextEpisodeActions' (-1), so _onKeyOk has to defer
		# to acceptNextEpisode itself while that prompt is up, or it would
		# permanently shadow "OK accepts the next episode" instead.
		"ok": (self._onKeyOk, _("Confirm rating / accept suggested title")),
		"cancel": (self._onKeyCancel, _("Cancel rating / dismiss suggestion")),
		"exitFunction": (self.exitFunction, _("Exit player")),
		"keyTv": (self.leavePlayer, _("Stop and return")),
		"stop": (self.leavePlayer, _("Stop and return")),
		# RED/BLUE both map to "seekManual" - while the rating panel is up,
		# RED/BLUE clear the pending vote instead (same reasoning as
		# _onKeyOk/_onKeyCancel: this map's priority (-2) beats ratingActions'
		# (-1), so the panel-aware check has to live in the handler that
		# actually runs).
		"seekManual": (self._onKeyRed, _("Manual seek / clear rating")),
		"playNext": (self.playNextEntry, _("Play next episode")),
		"playPrevious": (self.playPreviousEntry, _("Play previous episode")),
		"info": (self.showPlaybackInfo, _("Show playback info (long press: rate/favorite)")),
		"favorite": (self.showRatingPanel, _("Rate / mark as favorite")),
		# LEFT/RIGHT browse the "you might also like" carousel while it is
		# up, same reasoning as seekManual/_onKeyRed above - keymap.xml has
		# no LEFT/RIGHT binding at all in the DPS_Player context otherwise
		# (InfoBarSeek's own seekBack/seekFwd come from a *different*
		# context, "InfobarSeekActions", so normal arrow-key seeking outside
		# the carousel is untouched by adding this here).
		"left": (self._onKeyLeft, _("Seek back / previous suggestion")),
		"right": (self._onKeyRight, _("Seek forward / next suggestion")),
		# UP/DOWN scroll the carousel's summary text when it does not fit
		# the widget - a no-op outside the carousel (nothing else in
		# DP_Player used these keys before).
		"up": (self._onKeyUp, _("Scroll suggestion text up")),
		"down": (self._onKeyDown, _("Scroll suggestion text down")),
		}, -2)

		# Second trigger for the same Help screen, on LIST - see
		# DPH_ScreenHelper.DPH_Screen for why (remotes whose HELP button
		# does not reach the box as KEY_HELP).
		self["helpShortcut"] = HelpableActionMap(self, "DP_HelpShortcut",
		{
		"helpAlt": (self.showHelp, _("Show help")),
		}, -2)

		self.playbackInfoDialog = None
		self.playbackInfoShown = False

		# --- FAV-key rating/favorite panel (see DPH_RatingPanel) ---
		self.ratingPanelDialog = None
		self.ratingPanelShown = False
		self.ratingKind = None
		self.pendingFavorite = None        # Jellyfin: True/False while the panel is open
		self.pendingRatingDigit = None     # Plex: last star digit (1-5) pressed
		self.pendingRatingIsFull = False   # Plex: half/full toggle for that digit
		self.pendingRatingValue = None     # Plex: resulting 0-10 rating
		self.pendingRatingClear = False    # Plex: RED/BLUE was pressed - remove the rating entirely on confirm

		# InfoBarSeek's own "SeekActions" map (context "InfobarSeekActions",
		# prio -1) claims KEY_1/3/4/6/7/9 for the configurable manual-skip
		# feature ("seekdef:N") and, being registered first, wins ties at
		# the same priority - so 1/3/4/6/7/9 never reached this map while it
		# sat at -1 too (0/2/5/8, which "seekdef:" does not use, worked
		# fine). Enigma2 resolves one physical keypress to a single winner
		# across every bound context, by priority, not per-context
		# independently - so beating that map means a lower (more negative)
		# number here, not a different context name.
		# Kept disabled until showRatingPanel()/hideRatingPanel() toggle it -
		# HelpableActionMap only contributes to Help while enabled, so these
		# entries correctly appear in Help only while the rating panel is
		# actually on screen.
		self["ratingActions"] = HelpableActionMap(self, ["DPS_Player"],
		{
		"1": (lambda: self._onRatingDigit(1), _("Rate 1 star / mark favorite")),
		"2": (lambda: self._onRatingDigit(2), _("Rate 2 stars")),
		"3": (lambda: self._onRatingDigit(3), _("Rate 3 stars")),
		"4": (lambda: self._onRatingDigit(4), _("Rate 4 stars")),
		"5": (lambda: self._onRatingDigit(5), _("Rate 5 stars")),
		"0": (self._onRatingZero, _("Unmark favorite")),
		}, -2)
		self["ratingActions"].setEnabled(False)

		self["poster"] = Pixmap()
		self["shortDescription"] = Label()
		self["mediaTitle"] = StaticText()
		self["endingTime"] = Label()

		# init volume object
		self.volumeHandler = eDVBVolumecontrol.getInstance()
		# only images >= 05.08.2010, must use try/except
		try:
			self.volumeControlInstance = VolumeControl.instance
		except Exception:
			pass

		# Poster
		self.EXpicloadPoster = ePicLoad()

		# Separate decoder for the carousel's currently-highlighted
		# suggestion poster - it shows a different movie than the one
		# actually playing, so it cannot share EXpicloadPoster/self.ptr
		# above without clobbering the real poster.
		self.similarPicLoad = ePicLoad()

		# it will stop up/down/movielist buttons opening standard movielist whilst playing movie in plex
		if "MovieListActions" in self:
			self["MovieListActions"].setEnabled(False)

		self.__event_tracker = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evUser + 10: self.__evAudioDecodeError,
			iPlayableService.evUser + 11: self.__evVideoDecodeError,
			iPlayableService.evUser + 12: self.__evPluginError,
			iPlayableService.evBuffering: self.__evUpdatedBufferInfo,
			iPlayableService.evEOF: self.__evEOF,
			iPlayableService.evUpdatedInfo: self.__evUpdatedInfo,
		})

		self.resume = False

		# --- next episode prompt (see checkNextEpisodePrompt) ---
		self.nextEpisodeDialog = None
		self.nextEpisodeShown = False
		self.nextEpisodeDismissed = False
		self.nextEpisodeWatcher = None

		# A standalone movie has no "next" playlist entry to offer through
		# the same prompt (nextEpisodeSupported() requires isShow) - this
		# holds a "you might also like" carousel instead: 0+ 5-tuple
		# listing-row entries fetched once per movie via
		# DP_MediaLibrary.getSimilarItems() and cached here. isSimilarSuggestion
		# tells the shared ok/exitFunction/acceptNextEpisode handlers which
		# of the two (real next episode vs. this) is currently on screen.
		self.similarSuggestionEntries = []
		self.similarSuggestionIndex = 0
		self.isSimilarSuggestion = False

		# Same Help-only-while-enabled reasoning as ratingActions above. Note
		# these handlers never actually win the key dispatch (self["actions"]
		# sits at a lower/stronger priority and "ok"/"exitFunction" there
		# defer to acceptNextEpisode/dismissNextEpisode themselves while
		# this prompt is shown) - this map exists to hold the enabled state
		# Help reads, not to receive the keypress.
		self["nextEpisodeActions"] = HelpableActionMap(self, ["DPS_Player"],
		{
		"ok": (self.acceptNextEpisode, _("Accept / play now")),
		"exitFunction": (self.dismissNextEpisode, _("Dismiss")),
		}, -1)
		self["nextEpisodeActions"].setEnabled(False)

		self.onClose.append(self.cleanupNextEpisode)
		self.onClose.append(self.cleanupPlaybackInfo)
		self.onClose.append(self.cleanupRatingPanel)

		if not sessionData:
			if self.isExtraData:
				self.media_id = isExtraData[0]  # "125629"
				mediaFileUrl = isExtraData[1]  # "http://92.60.8.106:34400/services/iva/assets/853333/video.mp4?bitrate=1500"
				self.buildPlayerData(mediaFileUrl, isExtraData=True)
			else:
				# from here we go on
				self.onFirstExecBegin.append(self.playMedia)
		else:
			service1 = self.session.nav.getCurrentService()
			self.seek = service1 and service1.seek()
			self.setSeekState(self.SEEK_STATE_PLAY)

			self.onLayoutFinish.append(self.resumePlayerData)

	def __evUpdatedInfo(self):
		if self.resume and self.resumeStamp is not None and self.resumeStamp > 0.0:
			self.mhSeekHack = 0
			self.seekwatcherThread = eTimer()
			self.seekwatcherThread.callback.append(self.seekWatcher)
			self.seekwatcherThread.start(900, False)
			return

	#==============================================================================
	#
	#==============================================================================
	def resumePlayerData(self):
		printl("", self, "S")

		self.playerData = self.sessionData[0]

		self.ptr = self.sessionData[1]

		self.renderPoster()

		self.setPlayerData()

		self.startTimelineWatcher()

		if self.timelineWatcher is not None:
			self.timelineWatcher.start(5000, False)

		self.startNextEpisodeWatcher()

		printl("", self, "C")

	#==============================================================================
	# is called automatically
	#==============================================================================

	def createSummary(self):
		printl("", self, "S")

		printl("", self, "C")
		# return DreamplexPlayerSummary
		return InfoBarMoviePlayerSummary

	#==============================================================================
	#
	#==============================================================================
	def getVolume(self):
		printl("", self, "S")

		currentVolume = self.volumeHandler.getVolume()

		printl("", self, "C")
		return currentVolume

	#==============================================================================
	#
	#==============================================================================
	def setVolume(self, volume):
		printl("", self, "S")

		# set new volume
		self.volumeHandler.setVolume(volume, volume)
		if self.volumeControlInstance is not None:
			self.volumeControlInstance.volumeDialog.setValue(volume)  # update progressbar value
			self.volumeControlInstance.volumeDialog.show()
			self.volumeControlInstance.hideVolTimer.start(3000, True)

		printl("", self, "C")

	#==============================================================================
	#
	#==============================================================================
	def playMedia(self):
		printl("", self, "S")

		selection = self.listViewList[self.currentIndex]
		printl("selection: " + str(selection), self, "D")

		if selection[1].get('parentRatingKey'):  # this is the case with shows
			self.show_id = selection[1]['parentRatingKey']
			self.isShow = True
		else:
			self.isShow = False

		self.media_id = selection[1]['ratingKey']
		self.selection = selection
		server = selection[1]['server']

		# whatever was cached belongs to the item we are leaving. whatPoster
		# in particular: setPoster() only (re)builds it when None, which is
		# harmless for a show (buildPosterData() keys it on show_id, the
		# same for every episode of the same series) but was stale for a
		# movie starting a *different* movie within the same DP_Player
		# instance - e.g. accepting a "you might also like" suggestion -
		# since the old file path/pointer would otherwise still be there.
		self.whatPoster = None
		self.similarSuggestionEntries = []
		self.similarSuggestionIndex = 0

		self.setPoster()

		self.count, self.options, self.server = Singleton().getMediaLibrary().getMediaOptionsToPlay(self.media_id, server, False, myType=selection[1]['tagType'])

		self.selectMedia(self.count, self.options, self.server)

		# it has to be restarted for every episode: the "already offered" and
		# "dismissed by the user" states apply to a single episode
		self.startNextEpisodeWatcher()

		printl("", self, "C")

	#===========================================================
	#
	#===========================================================
	def selectMedia(self, count, options, server):
		printl("", self, "S")

		#if we have two or more files for the same movie, then present a screen
		self.options = options
		self.server = server
		self.dvdplayback = False

		if not self.options:
			response = Singleton().getMediaLibrary().getLastResponse()
			self.session.open(MessageBox, (_("Error:") + "\n%s") % response, MessageBox.TYPE_INFO)
		else:
			if count > 1 and not self.autoSelectFirstMedia:
				printl("we have more than one playable part ...", self, "I")
				indexCount = 0
				functionList = []

				for items in self.options:
					printl("item: " + str(items), self, "D")
					if items[1] is not None:
						name = items[1].split('/')[-1]
					else:
						size = convertSize(int(items[3]))
						duration = time.strftime('%H:%M:%S', time.gmtime(int(items[4])))
						# this is the case when there is no information of the real file name
						name = items[0] + " (" + items[2] + " / " + size + " / " + duration + ")"

					printl("name " + str(name), self, "D")
					functionList.append((name, indexCount, ))
					indexCount += 1

				self.session.openWithCallback(self.setSelectedMedia, ChoiceBox, title=_("Select media to play"), list=functionList)

			else:
				self.setSelectedMedia()

			printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setSelectedMedia(self, choice=None):
		printl("", self, "S")
		result = 0
		printl("choice: " + str(choice), self, "D")

		if choice is not None:
			result = int(choice[1])

		printl("result: " + str(result), self, "D")

		Singleton().getMediaLibrary().setPlaybackType(str(self.playbackMode))

		mediaFileUrl = Singleton().getMediaLibrary().mediaType({'key': self.options[result][0], 'file': self.options[result][1]}, self.server)
		printl("We have selected media at " + mediaFileUrl, self, "I")

		self.buildPlayerData(mediaFileUrl)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def buildPlayerData(self, mediaFileUrl, isExtraData=False):
		printl("", self, "S")

		self.playerData[self.currentIndex] = Singleton().getMediaLibrary().playLibraryMedia(self.media_id, mediaFileUrl, isExtraData=isExtraData)

		# populate addional data
		self.setPlayerData()

		self.playSelectedMedia()

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def playSelectedMedia(self):
		printl("", self, "S")

		if self.isExtraData:
			self.play()
		else:
			resumeStamp = self.playerData[self.currentIndex]['resumeStamp']
			printl("resumeStamp: " + str(resumeStamp), self, "I")

			if self.playerData[self.currentIndex]['fallback']:
				message = _("Sorry I didn't find the file on the provided locations")
				locations = _("Location:") + "\n " + self.playerData[self.currentIndex]['locations']
				suggestion = _("Please verify you direct local settings")
				fallback = _("I will now try to play the file via transcode.")

				self.session.openWithCallback(self.checkResume, MessageBox, _("Warning:") + "\n%s\n\n%s\n\n%s\n\n%s" % (message, locations, suggestion, fallback), MessageBox.TYPE_ERROR)
			else:
				self.checkResume(resumeStamp)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def checkResume(self, resumeStamp):
		printl("", self, "S")

		if resumeStamp > 0 and self.resumeMode:
			#mh - resume locks up too often so disable #
			self.session.openWithCallback(self.handleResume, MessageBox, _(" This file was partially played.\n\n Do you want to resume?"), MessageBox.TYPE_YESNO)

			#printl("mh: not resuming as it's fucked too often", self, "D")
			#resumeStamp = 0
			#self.play()

		elif self.forceResume:
			self.play(resume=True)

		else:
			self.play()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def handleResume(self, confirm):
		printl("", self, "S")

		if confirm:
			self.play(resume=True)

		else:
			self.play()

		printl("", self, "C")

	#==============================================================================
	#
	#==============================================================================
	def setPoster(self):
		"""
		set params for poster via ePicLoad object
		"""
		printl("", self, "S")

		self.EXscale = (AVSwitch().getFramebufferScale())

		self.EXpicloadPoster.setPara([self["poster"].instance.size().width(), self["poster"].instance.size().height(), self.EXscale[0], self.EXscale[1], 0, 1, "#002C2C39"])

		if self.whatPoster is None:
			self.buildPosterData()

		self.EXpicloadPoster.startDecode(self.whatPoster, 0, 0, False)

		self.ptr = self.EXpicloadPoster.getData()

		self.renderPoster()

		printl("", self, "C")

	#==============================================================================
	#
	#==============================================================================
	def renderPoster(self):
		printl("", self, "S")

		try:
			self["poster"].instance.setPixmap(self.ptr)
		except Exception:
			pass

		printl("", self, "C")
	#===========================================================================
	#
	#===========================================================================

	def setServiceReferenceData(self):
		printl("", self, "S")

		self.setEnigmaServiceId()

		self.sref = eServiceReference(self.ENIGMA_SERVICE_ID, 0, self.url)
		self.sref.setName(self.title)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setEnigmaServiceId(self):
		printl("", self, "S")

		# check for playable services
		printl("Checking for usable gstreamer service (builtin)... ", self, "I")

		# lets built the sref for the movieplayer out of the gathered information
		if self.url[:4] == "http":  # this means we are in streaming mode so we will use sref 4097
			self.ENIGMA_SERVICE_ID = self.ENIGMA_SERVICEGS_ID

		elif self.url[-3:] == ".ts" or self.url[-4:] == ".iso":  # seems like we have a real ts file ot a iso file so we will use sref 1
			self.ENIGMA_SERVICE_ID = self.ENIGMA_SERVICETS_ID

		elif self.url[-5:] == ".m2ts":
			self.ENIGMA_SERVICE_ID = self.ENIGMA_SERVIDEM2_ID

		else:  # if we have a real file but no ts but for eg mkv we will use sref 4097
			if self.isValidServiceId(self.ENIGMA_SERVICEGS_ID):
				printl("we are able to stream over 4097", self, "I")
				self.ENIGMA_SERVICE_ID = self.ENIGMA_SERVICEGS_ID
			else:
				raise Exception

		printl("self.ENIGMA_SERVICE_ID = " + str(self.ENIGMA_SERVICE_ID), self, "I")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def playNextEntry(self):
		printl("", self, "S")

		# this also covers the "next" key: the prompt belongs to the episode we
		# are leaving and must be closed before switching
		self.hideNextEpisodePrompt()

		# first we write back the state of the current file to the plex server
		self.handleProgress()

		printl("currentIndex: " + str(self.currentIndex), self, "D")
		# increase position
		self.currentIndex += 1

		printl("nextIndex: " + str(self.currentIndex), self, "D")
		printl("self.listCount: " + str(self.listCount), self, "D")

		# check if we are at the end of the list we start all over
		if self.currentIndex > self.listCount:
			self.currentIndex = 0

		printl("finalIndex: " + str(self.currentIndex), self, "D")

		# stop current playback if exists
		self.session.nav.stopService()

		# play
		self.playMedia()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def playPreviousEntry(self):
		printl("", self, "S")

		self.hideNextEpisodePrompt()

		# first we write back the state of the current file to the plex server
		self.handleProgress()

		self.currentIndex -= 1

		# check if we are at the begining of the list we start at the end
		if self.currentIndex < 0:
			self.currentIndex = self.listCount

		# stop current playback if exists
		self.session.nav.stopService()

		# play
		self.playMedia()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def play(self, resume=False):
		printl("", self, "S")

		self.session.nav.stopService()

		# populate self.sref with new data
		self.setServiceReferenceData()

		# start playback
		self.session.nav.playService(self.sref)

		service1 = self.session.nav.getCurrentService()
		self.seek = service1 and service1.seek()

		self.resume = resume
		#if resume == True and self.resumeStamp is not None and self.resumeStamp > 0.0:
		#	self.seekwatcherThread = eTimer()
		#	self.seekwatcherThread.callback.append(self.seekWatcher)
		#	self.seekwatcherThread_conn = self.seekwatcherThread.timeout.connect(self.seekWatcher)
		#	self.seekwatcherThread.start(990,False)

		self.startTimelineWatcher()

		#mh
		sesd = self.plexInstance.getSelectedEmbeddedSubtitleData()
		printl("mh: g_SelectedEmbeddedSubtitleData=" + str(sesd), self, "D")
		if sesd != None:
			self.subtitleData = sesd

		printl("mh: subtitleData=" + str(self.subtitleData), self, "D")

		if self.subtitleData is not None:
			if self.subtitleData["id"] != -1:
				printl("mh: subtitleData.id=" + str(self.subtitleData["id"]), self, "D")
				printl("starting subtitleWatcher ...")
				self.startSubtitleWatcher()
			#mh
			else:
				self.disableSubtitleNow()
		#mh
		else:
			self.disableSubtitleNow()

		printl("mh: playbackType=" + str(self.playbackType), self, "D")

		if self.playbackType == "2":
			self["bufferslider"].setValue(100)

			if self.timelineWatcher is not None:
				# we start here too because it seems that direct local does not hit the buffer full function
				self.timelineWatcher.start(5000, False)

			if self.subtitleWatcher is not None:
				self.subtitleWatcher.start(10000, False)

		else:
			self["bufferslider"].setValue(1)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def startSubtitleWatcher(self):
		printl("", self, "S")

		self.subtitleWatcher = eTimer()
		self.subtitleWatcher.callback.append(self.subtitleChecker)

		printl("", self, "C")

	#===========================================================================
	# parts from AudioSelction.py from fillList()
	#===========================================================================
	def subtitleChecker(self):
		printl("", self, "S")

		try:
			#printl("mh: stc 1", self, "S")
			subtitles = self.getCurrentServiceSubtitle()
			#printl("mh: stc 2", self, "S")
			subtitlelist = subtitles.getSubtitleList()
			#printl("mh: stc 3", self, "S")

			subtitleStreams = []
			printl("subtitles: " + str(subtitles), self, "D")
			printl("what: " + str(subtitlelist), self, "D")

			matched = False
			foundDefined = False

			if len(subtitlelist):
				for x in subtitlelist:

					number = str(x[1])
					description = "?"
					myLanguage = _("<unknown>")
					selected = ""

					if x[4] != "und":
						foundDefined = True  # mh

						if x[4] in LanguageCodes:
							myLanguage = LanguageCodes[x[4]][0]
						else:
							myLanguage = x[4]

					if x[0] == 0:
						description = "DVB"
						number = "%x" % (x[1])

					elif x[0] == 1:
						description = "TTX"
						number = "%x%02x" % (x[3], x[2])

					elif x[0] == 2:
						types = (_("<unknown>"), "UTF-8 text", "SSA", "AAS", ".SRT file", "VOB", "PGS (unsupported)")
						description = types[x[2]]

					printl("mh: myLanguage=" + myLanguage + " description=" + description, self, "D")

					subs = (x, "", number, description, myLanguage, selected)
					printl("mh: subs=" + str(subs), self, "D")

					myLanguageFromPlex = self.subtitleData["languageCode"]

					try:
						if myLanguageFromPlex in LanguageCodes:
							myLanguageFromPlex = LanguageCodes[myLanguageFromPlex][0]

						printl("myLanguage: " + str(myLanguage) + " / myLanguageFromPlex: " + str(myLanguageFromPlex), self, "D")

						#mh : external force subs are first in list and are undefined
						forceMatch = False
						if self.plexInstance.getServerConfig().useForcedSubtitles().getValue():
							if foundDefined == False:
								if myLanguage == "<unknown>":
									if description == "UTF-8 text":
										try:
											if self.playerData[self.currentIndex]['usingExtForcedSubs'] == True:
												forceMatch = True
												printl("mh: force match", self, "D")

										except Exception as e:
											printl("Subtitle Message (3): " + str(e), self, "D")
											pass

						if myLanguageFromPlex == myLanguage or forceMatch:  # check force match
							printl("we have a match ...", self, "D")

							if matched == False:
								subtitleStreams.append((x, "", number, description, myLanguage, selected))  # mh

								self.disableSubtitleNow()  # mh : fixes subs being enabled on audio selection dialog but not appearing until toggled - no idea why

								self.enableSubtitleNow(subs[0])
								self.subtitleWatcher.stop()
								matched = True
								break  # mh - uncomment to trace subsequent subs streams for debugging
							else:
								printl("already set first match - just continuing for debugging", self, "D")

						else:
							printl("mh: no match", self, "D")
							print(self.subtitleData)
							print(myLanguage)
							#mh //raise Exception

							# just for debugging
							subtitleStreams.append((x, "", number, description, myLanguage, selected))

					except Exception as e:
						printl("Subtitle Message (2): " + str(e), self, "D")
						pass

			printl("subtitleStreams: " + str(subtitleStreams), self, "D")

		except Exception as e:
			printl("Subtitle Message: " + str(e), self, "D")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def enableSubtitleNow(self, subtitles):
		printl("", self, "S")
		success = False
		try:
			self.setSelectedSubtitle(subtitles)
			self.setSubtitlesEnable()
			success = True

		except Exception as e:
			printl("Subtitle Message: " + str(e), self, "D")

			try:
				printl("maybe we are openpli, trying their subtitle function", self, "D")
				# maybe we are openpli
				self.enableSubtitle(subtitles)
				success = True

			except Exception as e:
				printl("Subtitle Message (2): " + str(e), self, "D")

		if success:
			printl("success", self, "D")  # mh

			global SUBTITLES_ENABLED
			global SUBTITLES_CONTENT
			SUBTITLES_ENABLED = True
			SUBTITLES_CONTENT = subtitles

		printl("", self, "C")

	#===========================================================================
	# mh:
	#===========================================================================
	def disableSubtitleNow(self):
		printl("", self, "S")
		success = False
		try:
			self.setSelectedSubtitle(None)
			self.setSubtitlesEnable(False)
			self.setSubtitlesDisable()
			success = True

		except Exception as e:
			printl("Subtitle Message: " + str(e), self, "D")

			try:
				printl("maybe we are openpli, trying their subtitle function", self, "D")
				# maybe we are openpli
				self.enableSubtitle(None)
				success = True

			except Exception as e:
				printl("Subtitle Message (2): " + str(e), self, "D")

		if True:  # success:
			printl("success", self, "D")  # mh

			global SUBTITLES_ENABLED
			global SUBTITLES_CONTENT
			SUBTITLES_ENABLED = False
			SUBTITLES_CONTENT = None

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================

	def startTimelineWatcher(self):
		printl("", self, "S")

		self.timelineWatcher = eTimer()
		self.timelineWatcher.callback.append(self.updateTimeline)

		if self.multiUserServer:
			printl("we are a multiuser server", self, "D")
			self.multiUser = True

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def pauseService(self):
		printl("", self, "S")

		if self.playbackType == "1" and self.universalTranscoder:
			self.transcoderHeartbeat = eTimer()
			self.transcoderHeartbeat.callback.append(self.keepTranscoderAlive)
			self.transcoderHeartbeat.start(10000, False)

		if self.timelineWatcher is not None:
			self.timelineWatcher.stop()

		super(DP_Player, self).pauseService()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def unPauseService(self):
		printl("", self, "S")

		self.hide()
		self.setSeekState(self.SEEK_STATE_PLAY)

		if self.transcoderHeartbeat is not None:
			self.transcoderHeartbeat.stop()

		if self.timelineWatcher is not None:
			self.timelineWatcher.start(30000, False)

		printl("", self, "S")
	#===========================================================================
	#
	#===========================================================================

	def getTitle(self):
		printl("", self, "S")

		printl("", self, "C")
		return str(self.playerData[self.currentIndex]['videoData']['title'])

	#===========================================================================
	#
	#===========================================================================
	def setPlayerData(self):
		printl("", self, "S")

		self.playbackData = self.playerData[self.currentIndex]
		self.videoData = self.playerData[self.currentIndex]['videoData']

		# not used for now
		#self.mediaData = self.playerData[self.currentIndex]['mediaData']

		# go through the data out of the function call
		self.resumeStamp = int(self.playbackData['resumeStamp']) / 1000  # plex stores seconds * 1000
		self.server = str(self.playbackData['server'])
		self.id = str(self.playbackData['id'])
		self.multiUserServer = self.playbackData['multiUserServer']
		self.url = str(self.playbackData['playUrl'])
		self.transcodingSession = str(self.playbackData['transcodingSession'])
		self.playbackType = str(self.playbackData['playbackType'])
		self.connectionType = str(self.playbackData['connectionType'])
		self.universalTranscoder = self.playbackData['universalTranscoder']
		self.localAuth = self.playbackData['localAuth']

		self.title = encodeThat(self.videoData['title'])
		self["mediaTitle"].setText(self.title)

		self.shortDescription = encodeThat(self.videoData['summary'])
		self["shortDescription"].setText(self.shortDescription)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def isValidServiceId(self, myId):
		printl("", self, "S")

		testSRef = eServiceReference(myId, 0, "Just a TestReference")
		info = eServiceCenter.getInstance().info(testSRef)

		printl("", self, "C")
		return info is not None

	#===========================================================================
	#
	#===========================================================================
	def __evUpdatedBufferInfo(self):
		#printl("", self, "S")

		if self.playbackType == "2":
			self.bufferFull()
		else:
			self.bufferInfo()

		#printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _onKeyOk(self):
		if self.ratingPanelShown:
			self._confirmRating()
		elif self.nextEpisodeShown:
			self.acceptNextEpisode()
		else:
			self.toggleShow()

	#===========================================================================
	# ESC also has to close the rating panel / playback info panel first,
	# since both are separate dialogs (see DPH_RatingPanel/DPH_PlaybackInfo)
	# that InfoBarShowHide's own hide() - bound here the rest of the time -
	# knows nothing about.
	#===========================================================================
	def _onKeyCancel(self):
		printl("ratingPanelShown=%s playbackInfoShown=%s" % (self.ratingPanelShown, self.playbackInfoShown), self, "D")
		if self.ratingPanelShown:
			self._cancelRating()
		elif self.playbackInfoShown:
			self.hidePlaybackInfo()
		else:
			self.hide()

	#===========================================================================
	# INFO/Guide key: a richer overview than the plain OK progress overlay -
	# poster, title, plot and metadata (year/genre/rating/duration/cast) -
	# shown for a fixed time or until ESC. self.ptr (the already-decoded
	# poster pixmap set up by setPoster()/renderPoster()) is reused as-is,
	# no second image decode.
	#===========================================================================
	def showPlaybackInfo(self):
		printl("", self, "S")

		if self.playbackInfoDialog is None:
			self.playbackInfoDialog = self.session.instantiateDialog(DPH_PlaybackInfo)
			self.playbackInfoDialog.onDismiss = self._onPlaybackInfoAutoDismissed

		parts = []
		year = self.videoData.get('year')
		if year:
			parts.append(str(year))
		genre = self.videoData.get('genre')
		if genre:
			parts.append(str(genre))
		duration = self.videoData.get('duration')
		try:
			totalMinutes = int(duration) // 60000  # duration is stored in ms
		except (TypeError, ValueError):
			totalMinutes = 0
		if totalMinutes > 0:
			parts.append(_("%d min") % totalMinutes)
		contentRating = self.videoData.get('contentRating')
		if contentRating:
			parts.append(str(contentRating))
		rating = self.videoData.get('rating')
		try:
			if rating:
				parts.append("★ %.1f" % float(rating))
		except (TypeError, ValueError):
			pass
		metaLine = "   •   ".join(parts)

		extra = []
		director = self.videoData.get('director')
		if director:
			extra.append(_("Director: %s") % director)
		cast = self.videoData.get('cast')
		if cast:
			extra.append(_("Cast: %s") % cast)
		summary = self.shortDescription or ""
		if extra:
			summary = (summary + "\n\n" if summary else "") + "\n".join(extra)

		self.playbackInfoShown = True
		self.playbackInfoDialog.showInfo(self.title, summary, metaLine, getattr(self, 'ptr', None))

		printl("", self, "C")

	def hidePlaybackInfo(self):
		self.playbackInfoShown = False
		if self.playbackInfoDialog is not None:
			self.playbackInfoDialog.hideInfo()

	def _onPlaybackInfoAutoDismissed(self):
		self.playbackInfoShown = False

	def cleanupPlaybackInfo(self):
		if self.playbackInfoDialog is not None:
			self.playbackInfoDialog.hideInfo()
			self.session.deleteDialog(self.playbackInfoDialog)
			self.playbackInfoDialog = None

	#===========================================================================
	# FAV key: opens the rating/favorite panel (see DPH_RatingPanel), seeded
	# with the item's current favorite/rating state (videoData['isFavorite']/
	# ['personalRating'], read alongside the rest of the metadata) so
	# reopening the panel shows what is actually saved, not a blank slate -
	# OK re-submits whatever is displayed, whether or not it was touched.
	#===========================================================================
	def showRatingPanel(self):
		printl("", self, "S")

		# No server-type check: the backend declares what kind of rating it
		# supports (see DP_MediaLibrary.RATING_KIND_*), and this only
		# chooses which widget matches that - a third backend reusing either
		# kind needs no changes here at all.
		ratingKind = self.plexInstance.getRatingKind()
		if ratingKind == RATING_KIND_NONE:
			printl("", self, "C")
			return

		# A long INFO/EPG press fires "info" (short-press flag) before the
		# "favorite" long-press flag, so the Guide panel may already be up -
		# close it rather than stacking both overlays.
		if self.playbackInfoShown:
			self.hidePlaybackInfo()

		self.ratingKind = ratingKind
		if self.ratingPanelDialog is None:
			self.ratingPanelDialog = self.session.instantiateDialog(DPH_RatingPanel)
			self.ratingPanelDialog.onDismiss = self._onRatingPanelAutoDismissed

		if ratingKind == RATING_KIND_FAVORITE:
			self.pendingFavorite = bool(self.videoData.get('isFavorite'))
			self.ratingPanelDialog.showFavorite(self.pendingFavorite)
		else:
			currentRating = self.videoData.get('personalRating')
			try:
				currentValue = int(round(float(currentRating))) if currentRating not in (None, "") else None
			except (TypeError, ValueError):
				currentValue = None
			self.pendingRatingDigit = None
			self.pendingRatingIsFull = False
			self.pendingRatingValue = currentValue
			self.pendingRatingClear = False
			self.ratingPanelDialog.showStars(currentValue)

		self.ratingPanelShown = True
		self["ratingActions"].setEnabled(True)

		printl("", self, "C")

	#===========================================================================
	# Jellyfin: "1" marks favorite. Plex: digits 1-5 pick the star to fill up
	# to, alternating half/full on repeated presses of the same digit -
	# pressing a different digit always starts that new position at half.
	#===========================================================================
	def _onRatingDigit(self, digit):
		printl("digit %d, ratingPanelShown=%s" % (digit, self.ratingPanelShown), self, "D")
		if not self.ratingPanelShown:
			return

		if self.ratingKind == RATING_KIND_FAVORITE:
			if digit == 1:
				self.pendingFavorite = True
				self.ratingPanelDialog.showFavorite(True)
			return

		self.pendingRatingDigit, self.pendingRatingIsFull, self.pendingRatingValue = \
			_nextPlexStarRating(self.pendingRatingDigit, self.pendingRatingIsFull, digit)
		self.pendingRatingClear = False
		self.ratingPanelDialog.showStars(self.pendingRatingValue)

	#===========================================================================
	# RED/BLUE (Plex only): clear the rating entirely on confirm, rather than
	# setting it to a value - "no rating" is a different server-side state
	# from "1 star" for Plex, and there was previously no way to get back to
	# it once you had rated something.
	#===========================================================================
	def _onKeyRed(self):
		if self.ratingPanelShown:
			if self.ratingKind == RATING_KIND_STARS:
				self._clearRating()
			else:
				self._onRatingZero()
		else:
			self.seekManual()

	def _clearRating(self):
		if not self.ratingPanelShown or self.ratingKind != RATING_KIND_STARS:
			return

		self.pendingRatingDigit = None
		self.pendingRatingIsFull = False
		self.pendingRatingValue = None
		self.pendingRatingClear = True
		self.ratingPanelDialog.showStars(None, cleared=True)

	#===========================================================================
	# Jellyfin only: "0" unmarks favorite.
	#===========================================================================
	def _onRatingZero(self):
		if not self.ratingPanelShown or self.ratingKind != RATING_KIND_FAVORITE:
			return

		self.pendingFavorite = False
		self.ratingPanelDialog.showFavorite(False)

	#===========================================================================
	#
	#===========================================================================
	def _confirmRating(self):
		printl("", self, "S")

		try:
			# submitRating()'s value meaning depends entirely on ratingKind
			# (see DP_MediaLibrary.submitRating) - DP_Player never calls a
			# backend-specific method (setFavorite/rateItem) directly.
			#
			# videoData was read once, when playback started - it is not
			# re-fetched from the server after this, so it has to be updated
			# here too or a re-opened panel (showRatingPanel() seeds itself
			# from videoData) would keep showing the pre-edit value for the
			# rest of this playback session even though the server-side
			# value did change.
			if self.ratingKind == RATING_KIND_FAVORITE and self.pendingFavorite is not None:
				self.plexInstance.submitRating(self.server, self.id, self.pendingFavorite)
				self.videoData['isFavorite'] = self.pendingFavorite
			elif self.ratingKind == RATING_KIND_STARS and self.pendingRatingClear:
				self.plexInstance.submitRating(self.server, self.id, None)
				self.videoData['personalRating'] = None
			elif self.ratingKind == RATING_KIND_STARS and self.pendingRatingValue is not None:
				self.plexInstance.submitRating(self.server, self.id, self.pendingRatingValue)
				self.videoData['personalRating'] = self.pendingRatingValue
		except Exception as e:
			printl("could not submit rating: " + str(e), self, "W")

		self.hideRatingPanel()

		printl("", self, "C")

	def _cancelRating(self):
		self.hideRatingPanel()

	def hideRatingPanel(self):
		self.ratingPanelShown = False
		self["ratingActions"].setEnabled(False)
		if self.ratingPanelDialog is not None:
			self.ratingPanelDialog.hideRating()

	def _onRatingPanelAutoDismissed(self):
		printl("rating panel dismissed (explicit close or its own display timer)", self, "D")
		self.ratingPanelShown = False
		self["ratingActions"].setEnabled(False)

	def cleanupRatingPanel(self):
		if self.ratingPanelDialog is not None:
			self.ratingPanelDialog.hideRating()
			self.session.deleteDialog(self.ratingPanelDialog)
			self.ratingPanelDialog = None

	#===========================================================================
	#
	#===========================================================================
	def toggleShow(self):
		#printl("", self, "S")

		if self.playbackType != "2":
			self.bufferInfo()

		super(DP_Player, self).toggleShow()

		#printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def bufferInfo(self):
		#printl("", self, "S")

		try:
			bufferInfo = self.session.nav.getCurrentService().streamed().getBufferCharge()

			self.bufferPercent = bufferInfo[0]
			self.buffer1 = bufferInfo[1]
			self.bufferAvgOutRate = bufferInfo[2]
			self.buffer3 = bufferInfo[3]
			self.buffersize = bufferInfo[4]

			if int(self.bufferPercent) > 10:
				self["bufferslider"].setValue(int(self.bufferPercent))
				#printl("Buffersize[4]: %d BufferPercent[0]: %d Buffer[1]: %d Buffer[3]: %d BufferAvgOutRate[2]: %d" % (self.buffersize, self.bufferPercent, self.buffer1, self.buffer3, self.bufferAvgOutRate), self, "D")
			else:
				self["bufferslider"].setValue(1)

			if self.bufferPercent > 95:
				self.bufferFull()

			if self.bufferPercent == 0 and not self.endReached and (bufferInfo[1] != 0 and bufferInfo[2] != 0):
				self.bufferEmpty()
		except Exception:
			pass

		#printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def __evAudioDecodeError(self):
		printl("", self, "S")

		try:
			currPlay = self.session.nav.getCurrentService()
			sTagAudioCodec = currPlay.info().getInfoString(iServiceInformation.sTagAudioCodec)
			printl("audio-codec %s can't be decoded by hardware" % sTagAudioCodec, self, "I")
			Notifications.AddNotification(MessageBox, _("This Box can't decode %s streams!") % sTagAudioCodec, type=MessageBox.TYPE_INFO, timeout=10)

		except Exception as e:
			printl("exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def __evVideoDecodeError(self):
		printl("", self, "S")

		try:
			currPlay = self.session.nav.getCurrentService()
			sTagVideoCodec = currPlay.info().getInfoString(iServiceInformation.sTagVideoCodec)
			printl("video-codec %s can't be decoded by hardware" % sTagVideoCodec, self, "I")
			Notifications.AddNotification(MessageBox, _("This Box can't decode %s streams!") % sTagVideoCodec, type=MessageBox.TYPE_INFO, timeout=10)

		except Exception as e:
			printl("exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def __evPluginError(self):
		printl("", self, "S")

		try:
			currPlay = self.session.nav.getCurrentService()
			message = currPlay.info().getInfoString(iServiceInformation.sUser + 12)
			printl("[PlexPlayer] PluginError " + message, self, "I")
			Notifications.AddNotification(MessageBox, _("Your Box can't decode this video stream!\n%s") % message, type=MessageBox.TYPE_INFO, timeout=10)

		except Exception as e:
			printl("exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def __evEOF(self):
		printl("", self, "S")

		printl("got evEOF", self, "W")

		try:
			err = self.session.nav.getCurrentService().info().getInfoString(iServiceInformation.sUser + 12)
			printl("Error: " + str(err), self, "W")

			if err != "":
				Notifications.AddNotification(MessageBox, _("Your Box can't decode this video stream!\n%s") % err, type=MessageBox.TYPE_INFO, timeout=10)

		except Exception as e:
			printl("exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	#noinspection PyUnusedLocal
	def seekWatcher(self, *args):
		printl("", self, "S")

		printl("seekWatcher started", self, "I")
		try:
			while self is not None and self.resumeStamp is not None:
				self.seekToStartPos()
				sleep(1)
		except Exception as e:
			printl("stopping due to exception in seektostartpos, eg. stopped playback before ready ..." + str(e), self, "W")

		printl("seekWatcher finished ", self, "I")
		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def seekToStartPos(self):
		printl("", self, "S")
		try:
			if self.resumeStamp is not None:
				service = self.session.nav.getCurrentService()
				seek = service and service.seek()
				if seek is not None:

					r = seek.getLength()
					if not r[0]:
						printl("got duration", self, "D")
						if r[1] == 0:
							printl("duration 0", self, "D")
							return
						length = r[1]
					else:
						# service.seek().getLength() reported an error (r[0]
						# truthy) instead of a duration - length never gets
						# set, so if this falls through to the seek below it
						# would crash on an undefined name. Logged so a
						# streamed-URL seek failure is diagnosable instead of
						# silently doing nothing.
						printl("getLength() failed, r=" + str(r), self, "W")
						printl("", self, "C")
						return

					r = seek.getPlayPosition()
					if not r[0]:
						printl("playbacktime " + str(r[1]), self, "D")

						if r[1] < 90000:  # ~2 sekunden

							self.mhSeekHack = self.mhSeekHack + 1
							if self.mhSeekHack < 5:

								printl("do not seek yet (mhSeekHack:" + str(self.mhSeekHack) + ") " + str(r[1]), self, "D")
								printl("", self, "C")
								return

							self.mhSeekHack = 0
					else:
						# this was the previously-silent exit: getPlayPosition()
						# reporting an error here aborts the seek with no clue
						# why - now logged with the raw (error, value) tuple.
						printl("getPlayPosition() failed, r=" + str(r), self, "W")
						printl("", self, "C")
						return
					elapsed = self.resumeStamp * 90000
					printl("seeking to " + str(elapsed) + " length " + str(length) + " ", self, "D")

					#mh //if elapsed < 90000:
					#mh //	printl("skip seeking < 10s", self, "D")
					#mh //	printl("", self, "C")
					#mh //	return

					self.doSeek(int(elapsed))
					self.resumeStamp = None
				else:
					printl("service.seek() returned None - service does not support seeking", self, "W")

		except Exception as e:
			printl("exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def bufferFull(self):
		#printl("", self, "S")

		if self.seekstate != self.SEEK_STATE_PLAY:
			printl("Buffer filled start playing", self, "I")
			self.setSeekState(self.SEEK_STATE_PLAY)

		if self.timelineWatcher is not None:
			self.timelineWatcher.start(5000, False)

		#printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def bufferEmpty(self):
		#printl("", self, "S")

		if self.timelineWatcher is not None:
			self.timelineWatcher.stop()

		#printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================

	def leavePlayer(self):
		printl("", self, "S")

		self.leavePlayerConfirmed(True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def exitFunction(self):
		printl("", self, "S")

		# "exitFunction" is bound here at priority -2, ahead of
		# nextEpisodeActions' own "exitFunction" (-1) - on a remote whose
		# EXIT/ESC button generates KEY_EXIT rather than KEY_ESC (common),
		# this ran unconditionally and left the player instead of just
		# closing whatever overlay is currently up, exactly the same class
		# of bug _onKeyCancel already guards against for KEY_ESC.
		if self.ratingPanelShown:
			self._cancelRating()
			printl("", self, "C")
			return

		if self.playbackInfoShown:
			self.hidePlaybackInfo()
			printl("", self, "C")
			return

		if self.nextEpisodeShown:
			self.dismissNextEpisode()
			printl("", self, "C")
			return

		if self.settings.exitFunction.getValue() == "2":
			self.close((True, (self.playerData, self.ptr, self.id, self.currentIndex)))

		elif self.settings.exitFunction.getValue() == "1":
			self.leavePlayer()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def leavePlayerConfirmed(self, answer):
		printl("", self, "S")

		if answer != "EOF":
			self.handleProgress()

		else:
			self.handleProgress(EOF=True)

		if self.playbackType == "1":
			self.stopTranscoding()

		if self.settings.lcd4linux.getValue():
			# preparePosterForExternalUsage() always sets self.tempPoster to
			# the intended path, even when the copy2() inside it silently
			# failed (e.g. no poster was ever downloaded for this item) - so
			# the file is not guaranteed to exist here.
			try:
				remove(self.tempPoster)
			except OSError as e:
				printl("could not remove tempPoster: " + str(e), self, "D")

		# we destroy here all variables to be sure that they are away
		if self.timelineWatcher is not None:
			self.timelineWatcher.stop()

		# we stop playback here
		self.session.nav.stopService()

		# if self.startedByRemotePlayer:
		# 	self.session.nav.playService(getLiveTv())

		self.close((False, ))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def doEofInternal(self, playing):
		printl("", self, "S")

		# The "you might also like" carousel is not something the user
		# already committed to (unlike the next-episode prompt below, which
		# a running countdown always resolves one way or another before EOF
		# can even arrive) - reaching the actual end of the movie must not
		# yank it off screen and dump the user back at the home screen while
		# they were still deciding. Report progress now regardless (the same
		# call the exit path would otherwise have made) so the watched state
		# is not left pending on however long they take to decide.
		if self.isSimilarSuggestion:
			self.handleProgress(EOF=True)
			if self.settings.similarSuggestionAutoplay.getValue():
				self.acceptNextEpisode()
			# else: stay put, frozen on the last frame, carousel still up
			printl("", self, "C")
			return

		# If EOF arrives while the prompt is still on screen, the countdown
		# would fire after the advance already done here, skipping two
		# episodes: it must be stopped before moving on.
		self.hideNextEpisodePrompt()

		if self.autoPlayMode:
			if not self.nextPlaylistEntryAvailable():
				self.leavePlayerConfirmed("EOF")
			else:
				#start next file
				self.playNextEntry()
		else:
			self.leavePlayerConfirmed("EOF")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	#===========================================================================
	# Next episode prompt
	#
	# Towards the end of an episode a panel with a countdown appears in the
	# bottom right corner: OK plays the next episode straight away, EXIT
	# dismisses the prompt, and if nothing happens playback moves on when the
	# countdown expires. Both the window in which it shows up and the length
	# of the countdown are configurable, and the feature can be turned off.
	#
	# The panel is a separate dialog because DP_Player inherits
	# InfoBarShowHide: a widget of the player skin would disappear along with
	# the infobar when the user hides it.
	#===========================================================================
	def startNextEpisodeWatcher(self):
		printl("", self, "S")

		self.nextEpisodeShown = False
		self.nextEpisodeDismissed = False

		if not self.nextEpisodeSupported():
			printl("not supported for this content", self, "D")
			printl("", self, "C")
			return

		if self.nextEpisodeWatcher is None:
			self.nextEpisodeWatcher = eTimer()
			self.nextEpisodeWatcher.callback.append(self.checkNextEpisodePrompt)

		# one second resolution: updateTimeline runs at 5s, or 30s depending on
		# the state, too coarse to catch the window in which to show up
		self.nextEpisodeWatcher.start(1000, False)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def nextEpisodeSupported(self):
		"""A show needs a next episode to follow; a standalone movie instead
		falls back to the "you might also like" carousel (_fetchSimilarSuggestions())."""
		if not self.settings.showNextEpisode.getValue():
			return False

		# isShow is set by playMedia from the metadata of the item and holds
		# for mixed libraries too; on the resume path it is not known yet, and
		# there the library type applies
		isShow = getattr(self, "isShow", None)
		if isShow is None:
			isShow = self.libraryName == "shows"

		if isShow:
			return self.nextPlaylistEntryAvailable()

		return self._fetchSimilarSuggestions()

	#===========================================================================
	# Fetches (once per movie - cached in similarSuggestionEntries) the
	# "you might also like" carousel entries for the current movie.
	#===========================================================================
	def _fetchSimilarSuggestions(self):
		if self.similarSuggestionEntries:
			return True

		try:
			self.similarSuggestionEntries = self.plexInstance.getSimilarItems(self.server, self.media_id)
		except Exception as e:
			printl("could not fetch similar-title suggestions: " + str(e), self, "W")
			self.similarSuggestionEntries = []

		self.similarSuggestionIndex = 0
		return bool(self.similarSuggestionEntries)

	#===========================================================================
	#
	#===========================================================================
	def checkNextEpisodePrompt(self):
		if self.nextEpisodeShown or self.nextEpisodeDismissed:
			return

		try:
			currentTime = int(self.getPlayPosition()[1] / 90000)
			totalTime = int(self.getPlayLength()[1] / 90000)
		except Exception:
			# position not available yet: we retry on the next tick
			return

		if totalTime <= 0 or currentTime <= 0:
			return

		remaining = totalTime - currentTime
		threshold = int(self.settings.nextEpisodeThreshold.getValue())

		if remaining > threshold or remaining < 0:
			return

		self.showNextEpisodePrompt(remaining)

	#===========================================================================
	#
	#===========================================================================
	def showNextEpisodePrompt(self, remaining):
		printl("remaining: " + str(remaining), self, "S")

		self.isSimilarSuggestion = bool(self.similarSuggestionEntries)

		if self.isSimilarSuggestion:
			# a suggestion is not something the user already committed to
			# watching, unlike a real next episode - no countdown unless the
			# user opted into autoplay, and it stays up till EXIT/OK/EOF
			countdown = int(self.settings.nextEpisodeCountdown.getValue()) if self.settings.similarSuggestionAutoplay.getValue() else 0
			countdown = min(countdown, max(1, remaining)) if countdown else 0
			label = _("Suggestion in %d s")
		else:
			# there is no point offering to wait longer than what is left
			countdown = min(int(self.settings.nextEpisodeCountdown.getValue()), max(1, remaining))
			label = None

		try:
			nextTitle = self.getNextEpisodeTitle()
		except Exception as e:
			printl("exception: " + str(e), self, "W")
			nextTitle = ""

		if self.nextEpisodeDialog is None:
			self.nextEpisodeDialog = self.session.instantiateDialog(DPH_NextEpisode)

		self.nextEpisodeShown = True
		self["nextEpisodeActions"].setEnabled(True)

		hint = None
		if self.isSimilarSuggestion:
			hint = (_("LEFT/RIGHT: browse     UP/DOWN: scroll     OK: play now     EXIT: cancel")
					if len(self.similarSuggestionEntries) > 1
					else _("UP/DOWN: scroll     OK: play now     EXIT: cancel"))

		self.nextEpisodeDialog.startCountdown(countdown, nextTitle, self.acceptNextEpisode, label=label, hint=hint)

		if self.isSimilarSuggestion:
			self._updateCarouselDisplay()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getNextEpisodeTitle(self):
		if self.isSimilarSuggestion:
			return self._similarSuggestionTitle()

		nextEntry = self.listViewList[self.currentIndex + 1]
		return str(nextEntry[1].get("title", ""))

	#===========================================================================
	#
	#===========================================================================
	def _similarSuggestionTitle(self):
		entry = self.similarSuggestionEntries[self.similarSuggestionIndex]
		title = str(entry[1].get("title", ""))
		total = len(self.similarSuggestionEntries)
		if total > 1:
			return "%d/%d   %s" % (self.similarSuggestionIndex + 1, total, title)
		return title

	#===========================================================================
	# LEFT/RIGHT dispatch (bound in the main -2 "actions" map, see its
	# comment on "left"/"right"): browse the carousel while it is up and has
	# more than one entry, otherwise the native arrow-key seek.
	#===========================================================================
	def _onKeyLeft(self):
		if self.isSimilarSuggestion and len(self.similarSuggestionEntries) > 1:
			self._onSimilarLeft()
		else:
			self.seekBack()

	def _onKeyRight(self):
		if self.isSimilarSuggestion and len(self.similarSuggestionEntries) > 1:
			self._onSimilarRight()
		else:
			self.seekFwd()

	def _onKeyUp(self):
		if self.isSimilarSuggestion and self.nextEpisodeDialog is not None:
			self.nextEpisodeDialog.scrollSummaryUp()

	def _onKeyDown(self):
		if self.isSimilarSuggestion and self.nextEpisodeDialog is not None:
			self.nextEpisodeDialog.scrollSummaryDown()

	#===========================================================================
	# Browsing itself: does not disturb the countdown (or lack of one).
	#===========================================================================
	def _onSimilarLeft(self):
		if not self.similarSuggestionEntries:
			return
		self.similarSuggestionIndex = (self.similarSuggestionIndex - 1) % len(self.similarSuggestionEntries)
		self._updateCarouselDisplay()

	def _onSimilarRight(self):
		if not self.similarSuggestionEntries:
			return
		self.similarSuggestionIndex = (self.similarSuggestionIndex + 1) % len(self.similarSuggestionEntries)
		self._updateCarouselDisplay()

	#===========================================================================
	# Pushes the highlighted carousel entry's title/poster/summary to the
	# dialog - called both for the initial display and every LEFT/RIGHT.
	#===========================================================================
	def _updateCarouselDisplay(self):
		if self.nextEpisodeDialog is None:
			return
		entry = self.similarSuggestionEntries[self.similarSuggestionIndex]
		summary = str(entry[1].get("summary") or entry[1].get("overview") or "")
		posterPtr = self._loadSimilarSuggestionPoster(entry)
		self.nextEpisodeDialog.updateTitle(self._similarSuggestionTitle())
		self.nextEpisodeDialog.updateArt(posterPtr, summary)

	#===========================================================================
	# Downloads (once per item, cached on disk like the main poster) and
	# decodes the poster for a single carousel entry - a synchronous, one-off
	# call per LEFT/RIGHT press, same trade-off buildPosterData()/
	# downloadPoster() already make for the movie actually playing.
	#===========================================================================
	def _loadSimilarSuggestionPoster(self, entry):
		entryData = entry[1]
		itemId = entryData.get('ratingKey') or entryData.get('id') or ''
		downloadUrl = entryData.get('thumb') or ''
		if not itemId or not downloadUrl or self.nextEpisodeDialog is None:
			return None

		try:
			imagePrefix = Singleton().getMediaLibrary().getServerName().lower()
			posterPath = self.settings.mediaFolderPath.getValue() + imagePrefix + "_suggestion_" + str(itemId) + "_" + self.width + "x" + self.height + "_v2.jpg"

			if not fileExists(posterPath):
				downloadUrl = downloadUrl.replace('&width=999&height=999', '&width=' + self.width + '&height=' + self.height)
				response = self.plexInstance.doRequest(downloadUrl)
				with open(posterPath, "wb") as local_file:
					local_file.write(response)

			widget = self.nextEpisodeDialog["carouselPoster"]
			self.similarPicLoad.setPara([widget.instance.size().width(), widget.instance.size().height(), self.EXscale[0], self.EXscale[1], 0, 1, "#002C2C39"])
			self.similarPicLoad.startDecode(posterPath, 0, 0, False)
			return self.similarPicLoad.getData()
		except Exception as e:
			printl("could not load suggestion poster: " + str(e), self, "W")
			return None

	#===========================================================================
	#
	#===========================================================================
	def acceptNextEpisode(self):
		printl("", self, "S")

		if not self.nextEpisodeShown:
			printl("", self, "C")
			return

		isSimilarSuggestion = self.isSimilarSuggestion
		self.hideNextEpisodePrompt()

		if isSimilarSuggestion:
			self._playSimilarSuggestion()
		elif self.nextPlaylistEntryAvailable():
			self.playNextEntry()

		printl("", self, "C")

	#===========================================================================
	# Replaces the current one-item "playlist" with the highlighted
	# suggestion and plays it, exactly like starting a movie from a list -
	# it is not spliced into listViewList (which may be a real, independently
	# navigable folder listing for a movie that has one) to avoid disturbing
	# the PREVIOUS/NEXT keys' normal behaviour there.
	#===========================================================================
	def _playSimilarSuggestion(self):
		printl("", self, "S")

		entry = self.similarSuggestionEntries[self.similarSuggestionIndex]
		self.similarSuggestionEntries = []
		self.similarSuggestionIndex = 0

		self.handleProgress()
		self.session.nav.stopService()

		self.listViewList = [entry]
		self.listCount = 0
		self.currentIndex = 0
		self.playMedia()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def dismissNextEpisode(self):
		printl("", self, "S")

		if not self.nextEpisodeShown:
			# no prompt on screen: EXIT falls back to its normal behaviour
			self.exitFunction()
			printl("", self, "C")
			return

		self.nextEpisodeDismissed = True
		self.hideNextEpisodePrompt()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def hideNextEpisodePrompt(self):
		self.nextEpisodeShown = False
		self.isSimilarSuggestion = False
		self["nextEpisodeActions"].setEnabled(False)

		if self.nextEpisodeWatcher is not None:
			self.nextEpisodeWatcher.stop()

		if self.nextEpisodeDialog is not None:
			self.nextEpisodeDialog.stopCountdown()

	#===========================================================================
	#
	#===========================================================================
	def cleanupNextEpisode(self):
		printl("", self, "S")

		if self.nextEpisodeWatcher is not None:
			self.nextEpisodeWatcher.stop()
			self.nextEpisodeWatcher = None

		if self.nextEpisodeDialog is not None:
			self.nextEpisodeDialog.stopCountdown()
			self.session.deleteDialog(self.nextEpisodeDialog)
			self.nextEpisodeDialog = None

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def nextPlaylistEntryAvailable(self):
		printl("", self, "S")

		# listCount is the LAST VALID INDEX (len - 1), not the number of
		# entries: a next entry exists unless we are already on the last one.
		available = self.currentIndex < self.listCount

		printl("available: " + str(available), self, "D")
		printl("", self, "C")
		return available

	#===========================================================================
	#
	#===========================================================================
	def handleProgress(self, EOF=False):
		printl("", self, "S")

		try:
			currentTime = int(self.getPlayPosition()[1] / 90000)
			totalTime = int(self.getPlayLength()[1] / 90000)
			printl("progress data available, ...", self, "D")

			if self.timelineWatcher is not None:
				self.timelineWatcher.stop()

			# Every call here (switching episode, leaving the player, EOF) is
			# a genuine end of that item's playback, not a periodic
			# heartbeat, so it is always reported as "stopped" - each
			# backend decides from the position/duration it is given whether
			# that counts as watched. No server-type check here: both
			# backends implement DP_MediaLibrary.reportPlaybackProgress().
			self.plexInstance.reportPlaybackProgress(self.server, self.id, currentTime, totalTime, stopped=True)

		except Exception:
			printl("no progress data maybe playback never started, returning ...", self, "D")
			return

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keepTranscoderAlive(self):
		printl("", self, "S")

		http = self.plexInstance.http
		self.plexInstance.doRequest(http + "://" + self.server + "/video/:/transcode/universal/ping?session=" + self.transcodingSession)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def stopTranscoding(self):
		printl("", self, "S")

		http = self.plexInstance.http
		if self.universalTranscoder:
			self.plexInstance.doRequest(http + "://" + self.server + "/video/:/transcode/universal/stop?session=" + self.transcodingSession)
		else:
			self.plexInstance.doRequest(http + "://" + self.server + "/video/:/transcode/segmented/stop?session=" + self.transcodingSession)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def isPlaying(self):
		printl("", self, "S")
		try:
			if self.seekstate != self.SEEK_STATE_PLAY and self.seekstate != self.SEEK_STATE_PAUSE:

				printl("", self, "C")
				return False
			else:

				printl("", self, "C")
				return True
		except Exception:

			printl("", self, "C")
			return False

	#===========================================================================
	# audioTrackWatcher
	#===========================================================================
	#noinspection PyUnusedLocal
	def audioTrackWatcher(self, *args):
		printl("", self, "S")

		try:
			while self.nTracks == False and self is not None:
				self.setAudioTrack()
				sleep(1)

		except Exception as e:
			printl("exception: " + str(e), self, "E")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def updateTimeline(self):
		printl("", self, "S")

		try:
			currentTime = int(self.getPlayPosition()[1] / 90000)
			totalTime = int(self.getPlayLength()[1] / 90000)
			progress = int((float(currentTime) / float(totalTime)) * 100)
		except Exception:
			return

		if self.calculateEndingTime:
			try:
				endingTime = localtime(time() + (totalTime - currentTime))
			except Exception as e:
				printl("something went wrong with ending time -> " + str(e), self, "D")
				endingTime = localtime()

			self["endingTime"].setText(strftime("%H:%M:%S", endingTime))
		else:
			self["endingTime"].hide()

		if self.multiUserServer:
			try:
				printl("currentTime: " + str(currentTime), self, "C")
				printl("totalTime: " + str(totalTime), self, "C")

				urlPath = self.server + "/:/timeline?containerKey=/library/sections/onDeck&key=/library/metadata/" + self.id + "&ratingKey=" + self.id

				seekState = self.seekstate

				if seekState == self.SEEK_STATE_PAUSE:
					printl("Movies PAUSED time: %s secs of %s @ %s%%" % (currentTime, totalTime, progress), self, "D")
					urlPath += "&state=paused&time=" + str(currentTime * 1000) + "&duration=" + str(totalTime * 1000)
					self.plexInstance.doRequest(urlPath)

				elif seekState == self.SEEK_STATE_PLAY:
					printl("Movies PLAYING time: %s secs of %s @ %s%%" % (currentTime, totalTime, progress), self, "D")
					urlPath += "&state=playing&time=" + str(currentTime * 1000) + "&duration=" + str(totalTime * 1000)
					self.plexInstance.doRequest(urlPath)

				# todo add buffering here if needed
					#urlPath += "&state=buffering&time=" + str(currentTime*1000)

				# todo add stopped here if needed
					#urlPath += "&state=stopped&time=" + str(currentTime*1000) + "&duration=" + str(totalTime*1000)

			except Exception as e:
				printl("exception: " + str(e), self, "E")
				return False

		printl("", self, "C")
		return True

	#===========================================================================
	#
	#===========================================================================
	def getPlayerState(self):
		printl("", self, "S")
		params = {}

		try:
			currentTime = self.getPlayPosition()[1] / 90000
			totalTime = self.getPlayLength()[1] / 90000

			params["duration"] = str(totalTime * 1000)

			params["progress"] = str(currentTime * 1000)

			if self.seekstate == self.SEEK_STATE_PAUSE:
				params["state"] = "paused"
			elif self.seekstate == self.SEEK_STATE_PLAY:
				params["state"] = "playing"
			elif self.seekstate == self.SEEK_STATE_STOP:
				params["state"] = "stopped"
			else:
				raise Exception

			params["lastKey"] = "/library/metadata/" + str(self.id)

			printl("", self, "C")
			return params

		except Exception:

			printl("", self, "C")
			return False

	#===========================================================================
	#
	#===========================================================================
	def getPlayer(self):
		printl("", self, "S")
		ret = None

		if self.seekstate == self.SEEK_STATE_PAUSE or self.seekstate == self.SEEK_STATE_PLAY:
			ret = {}
			if self.getMediaType() == "video":
				player = {}
				player['playerid'] = int(1)
				player['type'] = "video"
				ret["video"] = player

		printl("", self, "C")
		return ret

	#===========================================================================
	#
	#===========================================================================
	def getMediaType(self):
		printl("", self, "S")

		# todo someday there might be music and photo if needed
		mediaType = "video"

		printl("", self, "C")
		return mediaType

	#===========================================================================
	#
	#===========================================================================
	def setAudioTrack(self):
		printl("", self, "S")
		if not self.switchedLanguage:
			try:
				service = self.session.nav.getCurrentService()

				tracks = service and self.getServiceInterface("audioTracks")
				nTracks = tracks and tracks.getNumberOfTracks() or 0

				if not nTracks:
					printl("no tracks found yet ... retrying later", self, "D")
					return

				self.nTracks = True
				trackList = []

				for i in range(nTracks):
					audioInfo = tracks.getTrackInfo(i)
					lang = audioInfo.getLanguage()
					printl("lang: " + str(lang), self, "D")
					trackList += [str(lang)]

				systemLanguage = language.getLanguage()[:2]  # getLanguage returns e.g. "fi_FI" for "language_country"
				printl("found systemLanguage: " + systemLanguage, self, "I")
				#systemLanguage = "en"

				self.tryAudioEnable(trackList, systemLanguage, tracks)

			except Exception as e:
				printl("audioTrack exception: " + str(e), self, "W")

		printl("", self, "C")

	#===========================================================================
	# tryAudioEnable
	#===========================================================================
	def tryAudioEnable(self, alist, match, tracks):
		printl("", self, "S")
		printl("alist: " + str(alist), self, "D")
		printl("match: " + str(match), self, "D")
		index = 0
		for e in alist:
			e.lower()
			if e.find(match) >= 0:
				printl("audio track match: " + str(e), self, "I")
				sleep(2)
				tracks.selectTrack(index)

				printl("", self, "S")
				index += 1
			else:
				printl("no audio track match with " + str(e), self, "I")

		self.switchedLanguage = True
		printl("", self, "S")

	#===========================================================================
	# getServiceInterface
	#===========================================================================

	def getServiceInterface(self, iface):
		printl("", self, "S")
		service = self.session.nav.getCurrentService()  # self.service
		if service:
			attr = getattr(service, iface, None)
			if callable(attr):
				printl("", self, "C")
				return attr()

		printl("", self, "C")
		return None

	#===========================================================================
	#
	#===========================================================================
	def seekToMinute(self, minutes):
		printl("", self, "S")

		self.resumeStamp = int(minutes) * 60
		self.seekToStartPos()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def seekManual(self):
		printl("", self, "S")

		self.session.openWithCallback(self.seekToMinute, MinuteInput)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getPlayLength(self):
		printl("", self, "S")

		length = self.seek.getLength()

		printl("", self, "C")
		return length

	#===========================================================================
	#
	#===========================================================================
	def getPlayPosition(self):
		printl("", self, "S")

		try:
			position = self.seek.getPlayPosition()
		except Exception:
			return None

		printl("", self, "C")
		return position

	#===========================================================================
	#
	#===========================================================================
	def buildPosterData(self):
		printl("", self, "S")

		mediaPath = self.settings.mediaFolderPath.getValue()
		image_prefix = Singleton().getMediaLibrary().getServerName().lower()

		self.poster_postfix = "_poster_" + self.width + "x" + self.height + "_v2.jpg"

		if self.isShow:
			self.whatPoster = mediaPath + image_prefix + "_" + self.show_id + self.poster_postfix
		else:
			self.whatPoster = mediaPath + image_prefix + "_" + self.media_id + self.poster_postfix

		printl("what poster: " + self.whatPoster, self, "D")

		printl("builded poster data: " + str(self.whatPoster), self, "D")

		if not fileExists(self.whatPoster):
			self.downloadPoster()

		if self.settings.lcd4linux.getValue():
			self.preparePosterForExternalUsage()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def downloadPoster(self):
		printl("", self, "S")
		printl("self.width:" + str(self.width), self, "D")
		printl("self.height:" + str(self.height), self, "D")

		if self.isShow:
			download_url = self.selection[1]["art"]
		else:
			download_url = self.selection[1]["thumb"]

		download_url = download_url.replace('&width=999&height=999', '&width=' + self.width + '&height=' + self.height)

		printl("download url: " + download_url, self, "D")
		printl("what poster: " + self.whatPoster, self, "D")

		if download_url != "":
			response = self.plexInstance.doRequest(download_url)

			try:
				printl("starting download", self, "D")
				with open(self.whatPoster, "wb") as local_file:
					local_file.write(response)
					local_file.close()
			except Exception as e:
				printl("download error: " + str(e), self, "D")
				printl("last plexinstance error: " + str(self.plexInstance.getLastErrorMessage()), self, "D")
		else:
			printl("no posterdata in xml response, skipping ...", self, "D")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def preparePosterForExternalUsage(self):
		printl("", self, "S")

		tempPath = self.settings.logFolderPath.getValue()
		self.tempPoster = tempPath + "dreamplex.jpg"

		from shutil import copy2
		try:
			copy2(self.whatPoster, self.tempPoster)
		except Exception as e:
			printl("error copy poster from '%s' to '%s' / '%s'" % (self.whatPoster, self.tempPoster, str(e)), self, "D")

		printl("", self, "C")
