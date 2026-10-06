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
import threading

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
from Components.config import config
from Components.Pixmap import Pixmap
from Components.Label import Label
from Components.ActionMap import ActionMap
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

from .DPH_Singleton import Singleton
#from .DP_Summary import DreamplexPlayerSummary
from .DPH_ScreenHelper import DPH_ScreenHelper

from .__common__ import printl2 as printl, buildMediaChoiceName, encodeThat, runInThread, fireAndForget, PlaybackClock
from .__init__ import _  # _ is translation


# we need this to see the states for subtitles also in audioselction with yellow button
SUBTITLES_ENABLED = False
SUBTITLES_CONTENT = None

# how often playback progress is reported to the server. It used to be
# repeated in four places that could disagree; keep it in one.
TIMELINE_INTERVAL_MS = 5000


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
		# our own callback: the image's audioSelected() is gone since OpenATV 7.6
		self.session.openWithCallback(self.audioSelectionClosed, myAudioSelection, infobar=self.session.infobar or self)

	#===========================================================================
	#
	#===========================================================================
	def audioSelectionClosed(self, result=None):
		printl("result: " + str(result), self, "D")

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
	playSessionID = None
	playbackClock = None
	timelineWatcher = None
	seekwatcherThread = None
	whatPoster = None
	subtitleStreams = None
	subtitleLanguageCode = None
	subtitleWatcher = None

	#mh
	mhSeekHack = 0

	#===========================================================================
	#
	#===========================================================================

	def __init__(self, session, listViewList, currentIndex, libraryName, autoPlayMode, resumeMode, playbackMode, forceResume=False, isExtraData=False, sessionData=None, subtitleData=None, startedByRemotePlayer=False):
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
		self.onChangedEntry = []

		printl("mh: subtitleData=" + str(subtitleData), self, "D")

		# we add this for vix images due to their long press button support
		self.LongButtonPressed = False

		self.libraryName = libraryName

		self.plexInstance = Singleton().getPlexInstance()

		self.initScreen(self.skinName)

		self.bufferslider = Slider(0, 100)
		self["bufferslider"] = self.bufferslider

		self.bufferSeconds = 0
		self.bufferPercent = 0
		self.bufferSecondsLeft = 0
		self.bitrate = 0
		self.endReached = False

		self["actions"] = ActionMap(["DPS_Player"],
		{
		#"ok": self.ok,
		"cancel": self.hide,
		"exitFunction": self.exitFunction,
		"keyTv": self.leavePlayer,
		"stop": self.leavePlayer,
		"seekManual": self.seekManual,
		"playNext": self.playNextEntry,
		"playPrevious": self.playPreviousEntry,
		}, -2)

		self["poster"] = Pixmap()
		self["shortDescription"] = Label()
		self["mediaTitle"] = StaticText()
		self["endingTime"] = Label()

		# init volume object
		self.volumeHandler = eDVBVolumecontrol.getInstance()
		# only images >= 05.08.2010, must use try/except
		try:
			self.volumeControlInstance = VolumeControl.instance
		except:
			pass

		# Poster
		self.EXpicloadPoster = ePicLoad()

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
			# evUpdatedInfo fires again and again while a resume is pending,
			# and this used to build a NEW eTimer every time. Replacing a live
			# one drops the last Python reference to a timer whose callback
			# may be on the stack - enigma2 dispatches service events
			# synchronously from C++ - which is the shape of a use-after-free.
			# Keep the one object for the life of the player and just (re)arm
			# it: the next entry of a playlist needs it again. (Spotted by
			# DreamFin while chasing a native crash.)
			if self.seekwatcherThread is None:
				self.seekwatcherThread = eTimer()
				self.seekwatcherThread.callback.append(self.seekWatcher)
				self.mhSeekHack = 0

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
			self.timelineWatcher.start(TIMELINE_INTERVAL_MS, False)

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

		if "parentRatingKey" in selection[1]:  # this is the case with shows
			self.show_id = selection[1]['parentRatingKey']
			self.isShow = True
		else:
			self.isShow = False

		self.media_id = selection[1]['ratingKey']
		self.selection = selection
		server = selection[1]['server']

		self.setPoster()

		# asking the server for the media options is a network round trip:
		# keep it off the enigma2 main loop so the GUI cannot freeze
		def work():
			plex = Singleton().getPlexInstance()
			# the playback type first: getMediaOptionsToPlay() already reads it
			# (getTranscodeSettings() only builds the client capabilities when
			# it says "transcode"), so setting it later, in setSelectedMedia(),
			# left that read on the previous type - with a server configured as
			# streamed, the first transcoded play sent its capabilities empty
			plex.setPlaybackType(str(self.playbackMode))
			return plex.getMediaOptionsToPlay(self.media_id, server, False, myType=selection[1]['tagType'])

		runInThread(work, self.onMediaOptionsReady)

		printl("", self, "C")

	#===========================================================
	#
	#===========================================================
	def onMediaOptionsReady(self, mediaOptions, error):
		printl("", self, "S")

		if error is not None or not mediaOptions:
			printl("could not get media options: " + str(error), self, "E")
			self.session.open(MessageBox, (_("Error:") + "\n%s") % str(error), MessageBox.TYPE_INFO)

			printl("", self, "C")
			return

		self.count, self.options, self.server = mediaOptions

		self.selectMedia(self.count, self.options, self.server)

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
			response = Singleton().getPlexInstance().getLastResponse()
			self.session.open(MessageBox, (_("Error:") + "\n%s") % response, MessageBox.TYPE_INFO)
		else:
			if count > 1:
				printl("we have more than one playable part ...", self, "I")
				indexCount = 0
				functionList = []

				for items in self.options:
					printl("item: " + str(items), self, "D")
					name = buildMediaChoiceName(items)

					printl("name " + str(name), self, "D")
					functionList.append((name, indexCount, ))
					indexCount += 1

				self.session.openWithCallback(self.setSelectedMedia, ChoiceBox, title=_("Select media to play"), list=functionList)

			else:
				# only one version: play it directly with an explicit choice,
				# so a None choice can only mean "dialog cancelled"
				self.setSelectedMedia((None, 0))

			printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setSelectedMedia(self, choice=None):
		printl("", self, "S")
		result = 0
		printl("choice: " + str(choice), self, "D")

		if choice is None:
			# the version dialog was cancelled (EXIT) -> go back, do not play
			printl("selection cancelled, leaving player", self, "I")
			self.close((False, ))
			printl("", self, "C")
			return

		result = int(choice[1])

		printl("result: " + str(result), self, "D")

		# remember which VERSION was picked so the transcoder serves it too
		selectedOption = self.options[result]
		if len(selectedOption) > 7 and selectedOption[7] is not None:
			Singleton().getPlexInstance().setSelectedVersion(selectedOption[7])

		# the playback type was set before asking for the options (playMedia)
		mediaFileUrl = Singleton().getPlexInstance().mediaType({'key': self.options[result][0], 'file': self.options[result][1]}, self.server)
		printl("We have selected media at " + mediaFileUrl, self, "I")

		self.buildPlayerData(mediaFileUrl)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def buildPlayerData(self, mediaFileUrl, isExtraData=False):
		printl("", self, "S")

		# playLibraryMedia talks to the server (and starting a transcode
		# session can take seconds): off the main loop it goes
		def work():
			return Singleton().getPlexInstance().playLibraryMedia(self.media_id, mediaFileUrl, isExtraData=isExtraData)

		runInThread(work, self.onPlayerDataReady)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def onPlayerDataReady(self, playerData, error):
		printl("", self, "S")

		if error is not None or not playerData:
			printl("could not build player data: " + str(error), self, "E")
			self.session.open(MessageBox, (_("Error:") + "\n%s") % str(error), MessageBox.TYPE_INFO)

			printl("", self, "C")
			return

		self.playerData[self.currentIndex] = playerData

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
		except:
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
				self.timelineWatcher.start(TIMELINE_INTERVAL_MS, False)

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
					# the label above is translated, so it cannot also serve as the
					# sentinel further down: in Spanish it reads "<desconocido>" and
					# any comparison against "<unknown>" silently stops matching.
					languageIsUnknown = True
					selected = ""

					if x[4] != "und":
						foundDefined = True  # mh
						languageIsUnknown = False

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
						if self.plexInstance.getServerConfig().useForcedSubtitles.value:
							if foundDefined == False:
								if languageIsUnknown:
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

		# our own clock, because in transcoded HLS the decoder never has a
		# position to offer. Starts at the resume point so the very first
		# report already lands where playback actually is, not at zero
		self.playbackClock = PlaybackClock()
		try:
			startAt = int(self.resumeStamp) if self.resumeStamp else 0
		except (TypeError, ValueError):
			startAt = 0
		self.playbackClock.start(startAt)

		# the timer only fires after its interval, so the server would not
		# hear about this playback for another interval: report at once
		self.updateTimeline()

		# and start it right here. It used to be started from four other
		# places instead, and none of them won for streamed/transcoded
		# playback: resumePlayerData() started a timer that play() then
		# threw away by calling this method again (play() only started it
		# again for direct local), and the bufferFull event that would
		# have covered it never arrives on HLS. The result on hardware was
		# zero updateTimeline() calls for a whole playback - no progress
		# reported and the PlaybackClock left inert.
		self.timelineWatcher.start(TIMELINE_INTERVAL_MS, False)

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

		super(DP_Player, self).pauseService()

		if self.playbackClock is not None:
			self.playbackClock.pause()

		if self.timelineWatcher is not None:
			# report the pause before going quiet, otherwise the dashboard
			# keeps showing the stream as playing
			self.updateTimeline()
			self.timelineWatcher.stop()

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

		if self.playbackClock is not None:
			self.playbackClock.resume()

		if self.timelineWatcher is not None:
			# same 5s as everywhere else: at 30s the dashboard kept showing
			# the stream paused long after it had been resumed
			self.updateTimeline()
			self.timelineWatcher.start(TIMELINE_INTERVAL_MS, False)

		printl("", self, "S")
	#===========================================================================
	#
	#===========================================================================

	def getTitle(self):
		printl("", self, "S")

		printl("", self, "C")
		# applySkin asks for the title while the version-selection dialog is
		# still open, i.e. before playerData is filled - never crash here
		try:
			return str(self.playerData[self.currentIndex]['videoData']['title'])
		except (KeyError, TypeError, IndexError):
			return ""

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
		self.playSessionID = self.playbackData.get('playSessionID')
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
		except:
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
		"""One attempt at the resume seek. Repeated by the eTimer, not here.

		This runs on the enigma2 MAIN LOOP: despite its name the watcher is
		an eTimer, not a thread. It used to hold a `while` loop with a
		sleep(1) in it, which froze the whole GUI for as long as the resume
		took - key presses were simply dropped, and if the decoder never
		reported a position (which is what happens on transcoded HLS on some
		images) resumeStamp was never cleared and the loop never ended, so
		the GUI stayed frozen until the image's hang detector killed enigma2.
		The timer already repeats every 900ms, so one attempt per call is
		all that was ever needed.
		"""
		printl("", self, "S")

		if self.resumeStamp is None:
			# nothing left to do: stop repeating
			if self.seekwatcherThread is not None:
				self.seekwatcherThread.stop()
			printl("seekWatcher finished", self, "I")
			printl("", self, "C")
			return

		try:
			self.seekToStartPos()
		except Exception as e:
			printl("stopping due to exception in seektostartpos, eg. stopped playback before ready ..." + str(e), self, "W")
			if self.seekwatcherThread is not None:
				self.seekwatcherThread.stop()

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

					# only assigned when getLength() succeeds, and it is used
					# further down in a log line - without this default a
					# failing getLength() raised NameError there, the except
					# below swallowed it, and the resume was lost with nothing
					# but a warning (found by the DreamFin fork, same code)
					length = None

					r = seek.getLength()
					if not r[0]:
						printl("got duration", self, "D")
						if r[1] == 0:
							printl("duration 0", self, "D")
							return
						length = r[1]

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
						printl("", self, "C")
						return

					elapsed = self.resumeStamp * 90000
					# `time` here used to be the imported time function, so the
					# log read "seeking to <built-in function time>"
					printl("seeking to " + str(self.resumeStamp) + "s length " + str(length) + " ", self, "D")

					#mh //if elapsed < 90000:
					#mh //	printl("skip seeking < 10s", self, "D")
					#mh //	printl("", self, "C")
					#mh //	return

					self.doSeek(int(elapsed))
					self.resumeStamp = None

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
			self.timelineWatcher.start(TIMELINE_INTERVAL_MS, False)

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

		if config.plugins.dreamplex.exitFunction.value == "2":
			self.close((True, (self.playerData, self.ptr, self.id, self.currentIndex)))

		elif config.plugins.dreamplex.exitFunction.value == "1":
			self.leavePlayer()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def leavePlayerConfirmed(self, answer):
		printl("", self, "S")

		# the resume watcher must not outlive the player: it keeps firing on
		# the main loop while resumeStamp is set, and nothing else stops it
		if self.seekwatcherThread is not None:
			self.seekwatcherThread.stop()

		if answer != "EOF":
			self.handleProgress()

		else:
			self.handleProgress(EOF=True)

		if self.playbackType == "1":
			self.stopTranscoding()

		if config.plugins.dreamplex.lcd4linux.value:
			remove(self.tempPoster)

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
	def nextPlaylistEntryAvailable(self):
		printl("", self, "S")

		if self.listCount > 1:
			if (self.currentIndex + 1) < self.listCount:

				printl("", self, "C")
				return True

		printl("", self, "C")
		return False

	#===========================================================================
	#
	#===========================================================================
	def handleProgress(self, EOF=False):
		printl("", self, "S")

		try:
			# decoder when valid, own clock in HLS - reading the decoder
			# blindly used to leave currentTime negative here, which fell
			# through to the "end of file" branch below and scrobbled the
			# media as watched without anybody having watched it
			currentTime = self.getPlaybackPosition()
			totalTime = self.getMediaDuration()
			valid = currentTime is not None and currentTime > 0 and totalTime > 0

			if not EOF and not valid:
				printl("no valid play position, reporting nothing", self, "D")
				printl("", self, "C")
				return

			if currentTime is None:
				currentTime = 0
			printl("progress data available, ...", self, "D")

			if not EOF and currentTime is not None and currentTime > 0 and totalTime is not None and totalTime > 0:
				progress = currentTime / float(totalTime / 100.0)
				printl("played time is %s secs of %s @ %s%%" % (currentTime, totalTime, progress), self, "I")
			else:
				progress = 100
				printl("End of file reached", self, "D")

			# the reports below are sent while leaving the player: we do not
			# need their answer, so never block the GUI waiting for them
			if self.timelineWatcher is not None:
				self.timelineWatcher.stop()

				# closes the session on the server side: without it the box
				# lingers in the dashboard until the entry times out
				urlPath = self.buildTimelineUrl("stopped", currentTime, totalTime)
				fireAndForget(lambda url=urlPath: self.plexInstance.doRequest(url))

			#Legacy PMS Server server support before MultiUser version v0.9.8.0 and if we are not connected via plex.tv
			else:

				http = self.plexInstance.http

				if currentTime < 30:
					printl("Less that 30 seconds, will not set resume", self, "I")

				#If we are less than 95% complete, store resume time
				elif progress < 95:
					printl("Less than 95% progress, will store resume time", self, "I")
					progressUrl = http + "://" + self.server + "/:/progress?key=" + self.id + "&identifier=com.plexapp.plugins.library&time=" + str(currentTime * 1000)
					fireAndForget(lambda url=progressUrl: self.plexInstance.doRequest(url))

				#Otherwise, mark as watched
				else:
					printl("Movie marked as watched. Over 95% complete", self, "I")
					scrobbleUrl = http + "://" + self.server + "/:/scrobble?key=" + self.id + "&identifier=com.plexapp.plugins.library"
					fireAndForget(lambda url=scrobbleUrl: self.plexInstance.doRequest(url))

		except:
			printl("no progress data maybe playback never started, returning ...", self, "D")
			return

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keepTranscoderAlive(self):
		printl("", self, "S")

		# periodic ping: must not stall playback if the server is slow
		http = self.plexInstance.http
		pingUrl = http + "://" + self.server + "/video/:/transcode/universal/ping?session=" + self.transcodingSession
		fireAndForget(lambda url=pingUrl: self.plexInstance.doRequest(url))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def stopTranscoding(self):
		printl("", self, "S")

		# sent while leaving playback: no answer needed, never block on it
		http = self.plexInstance.http
		if self.universalTranscoder:
			stopUrl = http + "://" + self.server + "/video/:/transcode/universal/stop?session=" + self.transcodingSession
		else:
			stopUrl = http + "://" + self.server + "/video/:/transcode/segmented/stop?session=" + self.transcodingSession

		fireAndForget(lambda url=stopUrl: self.plexInstance.doRequest(url))

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
		except:

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
	def getMediaDuration(self):
		"""Length in seconds, from the metadata rather than the decoder.

		getPlayLength() has nothing to say about a transcoded HLS stream,
		so the only reliable source is what the server told us about the
		media when it was opened.
		"""
		try:
			duration = int(self.videoData.get("duration", 0))
		except (AttributeError, TypeError, ValueError):
			return 0

		if duration > 0:
			return int(duration / 1000)  # plex reports milliseconds

		# no metadata: fall back to the decoder, which is right for a
		# plain file even if it is useless for HLS
		try:
			length = self.getPlayLength()
			if length[0] == 0 and length[1] > 0:
				return int(length[1] / 90000)
		except Exception:
			pass

		return 0

	#===========================================================================
	#
	#===========================================================================
	def getPlaybackPosition(self):
		"""Seconds into the media: the decoder when it knows, our clock when
		it does not.

		getPlayPosition() returns (result, pts) and the pts only means
		something when result is 0 - which in transcoded HLS is never, so
		there the PlaybackClock estimate is all there is. When the decoder
		IS valid (plain files) it wins and the clock is resynced to it.
		"""
		try:
			position = self.getPlayPosition()
			if position[0] == 0:
				seconds = int(position[1] / 90000)
				if seconds >= 0:
					if self.playbackClock is not None:
						self.playbackClock.syncTo(seconds)
					return seconds
		except Exception:
			pass

		if self.playbackClock is not None:
			return self.playbackClock.tell()

		return None

	#===========================================================================
	#
	#===========================================================================
	def doSeek(self, pts):
		# keep the clock on the jump target, otherwise every resume or
		# absolute seek in HLS would leave the estimate at the old spot
		if self.playbackClock is not None and pts is not None and pts >= 0:
			self.playbackClock.syncTo(int(pts / 90000))

		super(DP_Player, self).doSeek(pts)

	#===========================================================================
	#
	#===========================================================================
	def doSeekRelative(self, pts):
		if self.playbackClock is not None and pts is not None:
			self.playbackClock.add(int(pts / 90000))

		super(DP_Player, self).doSeekRelative(pts)

	#===========================================================================
	#
	#===========================================================================
	def buildTimelineUrl(self, state, currentTime, totalTime):
		"""Timeline report the server builds its "now playing" entry from.

		`identifier` and `X-Plex-Session-Identifier` are what upstream left
		out: without them the server still moves the resume point, but it
		never shows the box as playing anything.
		"""
		urlPath = self.server + "/:/timeline?containerKey=/library/sections/onDeck"
		urlPath += "&identifier=com.plexapp.plugins.library"
		urlPath += "&key=/library/metadata/" + self.id + "&ratingKey=" + self.id
		urlPath += "&state=" + state
		urlPath += "&time=" + str(currentTime * 1000) + "&duration=" + str(totalTime * 1000)

		if self.playSessionID:
			urlPath += "&X-Plex-Session-Identifier=" + str(self.playSessionID)

		return urlPath

	#===========================================================================
	#
	#===========================================================================
	def updateTimeline(self):
		printl("", self, "S")

		try:
			# decoder position when valid, own clock in transcoded HLS -
			# upstream read the decoder blindly and reported garbage like
			# time=-60002501940670000, which the server drops on the floor
			currentTime = self.getPlaybackPosition()

			# the length has to come from the metadata: a transcoded HLS
			# stream does not report one, so getPlayLength() answers with
			# garbage there and asking it would silence every report
			totalTime = self.getMediaDuration()

			if currentTime is None or totalTime <= 0:
				printl("no position or duration to report", self, "D")
				printl("", self, "C")
				return True

			progress = int((float(currentTime) / float(totalTime)) * 100)
		except:
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

		try:
			printl("currentTime: " + str(currentTime), self, "C")
			printl("totalTime: " + str(totalTime), self, "C")

			# only a real pause is "paused"; everything else - playing,
			# buffering (throttled server), fast forward - is the user
			# watching, so report "playing". The old code only accepted
			# SEEK_STATE_PLAY and dropped every report while the server
			# throttled, which is most of a well-buffered stream
			if self.seekstate == self.SEEK_STATE_PAUSE:
				state = "paused"
			else:
				state = "playing"

			printl("Movies %s time: %s secs of %s @ %s%%" % (state.upper(), currentTime, totalTime, progress), self, "D")

			# this runs on a timer WHILE playing: a slow server here would
			# stutter the GUI on every tick, so fire it in the background
			urlPath = self.buildTimelineUrl(state, currentTime, totalTime)
			fireAndForget(lambda url=urlPath: self.plexInstance.doRequest(url))

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

		except:

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

				for i in xrange(nTracks):
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

		# the dialog can be cancelled, which answers None
		if minutes is None:
			printl("minute input cancelled", self, "D")
			printl("", self, "C")
			return

		try:
			seconds = max(0, int(minutes) * 60)
		except (TypeError, ValueError):
			printl("not a usable minute: " + str(minutes), self, "W")
			printl("", self, "C")
			return

		# never past the end of the media
		totalTime = self.getMediaDuration()
		if totalTime > 0 and seconds > totalTime:
			printl("clamping %s to the end of the media (%s)" % (seconds, totalTime), self, "D")
			seconds = totalTime

		# jump straight away instead of going through seekToStartPos(): that
		# one refuses to seek until the decoder reports where it is, and on
		# transcoded HLS it never does, so the jump was dropped in silence -
		# the minute dialog worked and nothing happened. seekToStartPos()
		# stays as it is: its retry logic is right for resuming AT START.
		printl("seeking to minute " + str(minutes) + " (" + str(seconds) + "s)", self, "I")
		self.doSeek(seconds * 90000)

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
		except:
			return None

		printl("", self, "C")
		return position

	#===========================================================================
	#
	#===========================================================================
	def buildPosterData(self):
		printl("", self, "S")

		mediaPath = config.plugins.dreamplex.mediafolderpath.value
		image_prefix = Singleton().getPlexInstance().getServerName().lower()

		self.poster_postfix = "_poster_" + self.width + "x" + self.height + "_v2.jpg"

		if self.isShow:
			self.whatPoster = mediaPath + image_prefix + "_" + self.show_id + self.poster_postfix
		else:
			self.whatPoster = mediaPath + image_prefix + "_" + self.media_id + self.poster_postfix

		printl("what poster: " + self.whatPoster, self, "D")

		printl("builded poster data: " + str(self.whatPoster), self, "D")

		if not fileExists(self.whatPoster):
			self.downloadPoster()

		if config.plugins.dreamplex.lcd4linux.value:
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

		tempPath = config.plugins.dreamplex.logfolderpath.value
		self.tempPoster = tempPath + "dreamplex.jpg"

		from shutil import copy2
		try:
			copy2(self.whatPoster, self.tempPoster)
		except Exception as e:
			printl("error copy poster from '%s' to '%s' / '%s'" % (self.whatPoster, self.tempPoster, str(e)), self, "D")

		printl("", self, "C")
