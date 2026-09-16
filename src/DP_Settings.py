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
#=================================
#IMPORT
#=================================
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ConfigList import ConfigListScreen
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components.config import config, getConfigListEntry, configfile
from Components.Label import Label
from Components.Pixmap import Pixmap

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from . import Singleton
from .DP_SettingsStorage import SettingsStorage

from .__common__ import printl2 as printl
from . import _  # _ is translation

from .DP_PathSelector import DPS_PathSelector
from .DPH_ScreenHelper import DPH_PlexScreen
from .DP_ViewFactory import getGuiElements

#===============================================================================
#
#===============================================================================


class DPS_Settings(Screen, ConfigListScreen, HelpableScreen, DPH_PlexScreen):

	_hasChanged = False
	_session = None
	skins = None

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		HelpableScreen.__init__(self)
		DPH_PlexScreen.__init__(self)

		self.guiElements = getGuiElements()

		self.cfglist = []
		ConfigListScreen.__init__(self, self.cfglist, session, on_change=self._changed)

		self._hasChanged = False

		settings: SettingsStorage = Singleton().getSettingsInstance()
		self._skinNameAtOpen = settings.skinName.getValue()

		self["Title"] = Label(_("System Settings"))
		self["btn_greenText"] = Label()
		self["btn_green"] = Pixmap()

		self["help"] = StaticText()

		self["setupActions"] = ActionMap(["SetupActions", "ColorActions", "DPS_Settings"],
		{
			"green": self.keySave,
			"red": self.keyCancel,
			"cancel": self.keyCancel,
			"ok": self.ok,
			"left": self.keyLeft,
			"right": self.keyRight,
			"bouquet_up": self.keyBouquetUp,
			"bouquet_down": self.keyBouquetDown,
		}, -2)

		# Second trigger for the same Help screen, on LIST - see
		# DPH_ScreenHelper.DPH_Screen for why (remotes whose HELP button
		# does not reach the box as KEY_HELP).
		self["helpShortcut"] = HelpableActionMap(self, "DP_HelpShortcut",
		{
			"helpAlt": (self.showHelp, _("Show help")),
		}, -2)

		self.createSetup()

		self["config"].onSelectionChanged.append(self.updateHelp)
		self.onLayoutFinish.append(self.finishLayout)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def finishLayout(self):
		printl("", self, "S")

		# first we set the pics for buttons
		self.setColorFunctionIcons()

		self["btn_greenText"].hide()
		self["btn_green"].hide()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def createSetup(self):
		printl("", self, "S")

		separator = "".ljust(240, "_")

		settings: SettingsStorage = Singleton().getSettingsInstance()

		self.cfglist = []

		# GENERAL SETTINGS
		self.cfglist.append(getConfigListEntry(_("General Settings ") + separator, settings.about.getConfigElement(), _(" ")))
		self.cfglist.append(getConfigListEntry(_("> Boxname"), settings.boxName.getConfigElement(), _("Enter the name of your box, e.g. Livingroom.")))
		self.cfglist.append(getConfigListEntry(_("> Used Skin"), settings.skinName.getConfigElement(), _("If you change the skin you have to restart at least the GUI!")))
		self.cfglist.append(getConfigListEntry(_("> Show Plugin in Main Menu"), settings.showInMainMenu.getConfigElement(), _("Use this to start the plugin direct in the main menu.")))
		self.cfglist.append(getConfigListEntry(_("> Use Cache for Sections"), settings.useCache.getConfigElement(), _("Save server answers in cache to speed up a bit.")))
		self.cfglist.append(getConfigListEntry(_("> Use Picture Cache"), settings.usePicCache.getConfigElement(), _("Use this only if you do have enough space on your hdd drive or flash.")))
		self.cfglist.append(getConfigListEntry(_("> Show Player Poster on external LCD"), settings.lcd4linux.getConfigElement(), _("e.g. lcd4linux")))

		# USERINTERFACE SETTINGS
		self.cfglist.append(getConfigListEntry(_("Userinterface Settings ") + separator, settings.about.getConfigElement(), _(" ")))
		self.cfglist.append(getConfigListEntry(_("> Summerize Servers"), settings.summerizeServers.getConfigElement(), _("Summerize servers in an additional menu step. (plex.tv only)")))
		self.cfglist.append(getConfigListEntry(_("> Summerize Sections"), settings.summerizeSections.getConfigElement(), _("Summerize sections in an additional menu step.")))
		self.cfglist.append(getConfigListEntry(_("> Show Filter for Section"), settings.showFilter.getConfigElement(), _("Show additional filter in an additional menu step e.g. OnDeck")))
		self.cfglist.append(getConfigListEntry(_("> Show Seen/Unseen count in TvShows"), settings.showUnSeenCounts.getConfigElement(), _("Calculate and show them for tv shows.")))
		self.cfglist.append(getConfigListEntry(_("> Start with Filtermode"), settings.startWithFilterMode.getConfigElement(), _("Start with filtermode in any media view.")))
		self.cfglist.append(getConfigListEntry(_("> Exit function in Player"), settings.exitFunction.getConfigElement(), _("Specifiy what the exit button in the player should do.")))

		self.cfglist.append(getConfigListEntry(_("> Offer next episode"), settings.showNextEpisode.getConfigElement(), _("Towards the end of an episode (or a related-title suggestion towards the end of a movie), offer to jump to the next one.")))
		if settings.showNextEpisode.getValue():
			self.cfglist.append(getConfigListEntry(_(">> Show it this many seconds before the end"), settings.nextEpisodeThreshold.getConfigElement(), _("How long before the end of the episode the offer appears.")))
			self.cfglist.append(getConfigListEntry(_(">> Countdown before playing next"), settings.nextEpisodeCountdown.getConfigElement(), _("If you do nothing, the next episode starts after this many seconds.")))
			self.cfglist.append(getConfigListEntry(_(">> Autoplay the suggested movie"), settings.similarSuggestionAutoplay.getConfigElement(), _("If off (default), the related-title suggestion for a movie waits for OK and never starts itself.")))

		self.cfglist.append(getConfigListEntry(_("> Main menu hero rotation (seconds, 0=off)"), settings.heroRotationInterval.getConfigElement(), _("The Carousel skin's main-menu banner switches to another suggested title after this many seconds. 0 keeps showing the same one.")))
		if settings.heroRotationInterval.getValue():
			self.cfglist.append(getConfigListEntry(_(">> Refresh suggestions after this many rotations"), settings.heroRefetchAfterLoops.getConfigElement(), _("How many times the banner cycles through its current list of suggestions before asking the server for a new one.")))
		self.cfglist.append(getConfigListEntry(_("> Max hero suggestions to request"), settings.heroMaxItems.getConfigElement(), _("Upper limit only - the server may return fewer, depending on what it has to offer.")))

		self.cfglist.append(getConfigListEntry(_("> Show Backdrops as Videos"), settings.useBackdropVideos.getConfigElement(), _("Use this if you have m1v videos as backdrops")))
		self.cfglist.append(getConfigListEntry(_("> Stop Live TV on startup"), settings.stopLiveTvOnStartup.getConfigElement(), _("Stop live TV. Enables 'play themes', 'use backdrop videos'")))

		# playing themes stops live tv for this reason we enable this only if live stops on startup is set
		# also backdrops as video needs to turn of live tv
		if settings.stopLiveTvOnStartup.getValue():
			# if backdrop videos are active we have to turn off theme playback
			if settings.useBackdropVideos.getValue():
				settings.playTheme.setValue(False)
			else:
				self.cfglist.append(getConfigListEntry(_(">> Play Themes in TV Shows"), settings.playTheme.getConfigElement(), _("Plays tv show themes automatically.")))
		else:
			# if the live startup stops is not set we have to turn of playtheme automatically
			settings.playTheme.setValue(False)
			#settings.useBackdropVideos.setValue(False)

		if settings.useBackdropVideos.getValue():
			settings.fastScroll.setValue(False)
			settings.liveTvInViews.setValue(False)
		else:
			self.cfglist.append(getConfigListEntry(_("> Use fastScroll as default"), settings.fastScroll.getConfigElement(), _("No update for addiontal informations in media views to speed up.")))
			if not settings.stopLiveTvOnStartup.getValue():
				self.cfglist.append(getConfigListEntry(_("> Show liveTv in Views instead of backdrops"), settings.liveTvInViews.getConfigElement(), _("Show live tv while you are navigating through your libs.")))

		self.cfglist.append(getConfigListEntry(_("> Show additional data for plex.tv sections"), settings.showDetailsInList.getConfigElement(), _("If server summerize is off you can here add additional information for better overview.")))
		if settings.showDetailsInList.getValue():
			self.cfglist.append(getConfigListEntry(_("> Detail type for additional data"), settings.showDetailsInListDetailType.getConfigElement(), _("Specifiy the type of additional data.")))

		# VIEW SETTINGS
		self.cfglist.append(getConfigListEntry(_("Path Settings ") + separator, settings.about.getConfigElement(), _(" ")))
		self.cfglist.append(getConfigListEntry(_("> Default View for Movies"), settings.defaultMovieView.getConfigElement(), _("Specify what view type should start automatically.")))
		self.cfglist.append(getConfigListEntry(_("> Default View for Shows"), settings.defaultShowView.getConfigElement(), _("Specify what view type should start automatically.")))
		self.cfglist.append(getConfigListEntry(_("> Default View for Music"), settings.defaultMusicView.getConfigElement(), _("Specify what view type should start automatically.")))

		# PATH SETTINGS
		self.cfglist.append(getConfigListEntry(_("Path Settings ") + separator, settings.about.getConfigElement(), _(" ")))

		self.mediafolderpath = getConfigListEntry(_("> Media Folder Path"), settings.mediaFolderPath.getConfigElement(), _("/hdd/dreamplex/medias"))
		self.cfglist.append(self.mediafolderpath)

		self.configfolderpath = getConfigListEntry(_("> Config Folder Path"), settings.configFolderPath.getConfigElement(), _("/hdd/dreamplex/config"))
		self.cfglist.append(self.configfolderpath)

		self.cachefolderpath = getConfigListEntry(_("> Cache Folder Path"), settings.cacheFolderPath.getConfigElement(), _("/hdd/dreamplex/cache"))
		self.cfglist.append(self.cachefolderpath)

		self.playerTempPath = getConfigListEntry(_("> Player Temp Path"), settings.playerTempPath.getConfigElement(), _("/tmp"))
		self.cfglist.append(self.playerTempPath)

		self.logfolderpath = getConfigListEntry(_("> Log Folder Path"), settings.logFolderPath.getConfigElement(), _("/tmp"))
		self.cfglist.append(self.logfolderpath)

		# REMOTE
		self.cfglist.append(getConfigListEntry(_("Remote Settings ") + separator, settings.about.getConfigElement(), _(" ")))
		self.cfglist.append(getConfigListEntry(_("> Activate Remote Player"), settings.remoteAgent.getConfigElement(), _("Activate to be able to use with any app with remote function for Plex.")))
		if settings.remoteAgent.getValue():
			self.cfglist.append(getConfigListEntry(_("> Remote Player Port"), settings.remotePort.getConfigElement(), _("Change the port to your needs.")))

		# MISC
		self.cfglist.append(getConfigListEntry(_("Misc Settings ") + separator, settings.about.getConfigElement(), _(" ")))
		self.cfglist.append(getConfigListEntry(_("> Debug Mode"), settings.debugMode.getConfigElement(), _("Enable only if needed. Slows down rapidly.")))

		if settings.debugMode.getValue():
			self.cfglist.append(getConfigListEntry(_("> Write debugfile"), settings.writeDebugFile.getConfigElement(), _("Without this option we just print to console.")))

		self["config"].list = self.cfglist
		self["config"].l.setList(self.cfglist)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _changed(self):
		printl("", self, "S")

		self._hasChanged = True

		self["btn_greenText"].show()
		self["btn_greenText"].setText(_("Save"))
		self["btn_green"].show()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def updateHelp(self):
		printl("", self, "S")

		cur = self["config"].getCurrent()
		printl("cur: " + str(cur), self, "D")
		self["help"].text = cur and cur[2] or "empty"

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def ok(self):
		printl("", self, "S")

		cur = self["config"].getCurrent()

		if cur == self.mediafolderpath:
			self.session.openWithCallback(self.savePathConfig, DPS_PathSelector, self.mediafolderpath[1].value, "media")

		elif cur == self.configfolderpath:
			self.session.openWithCallback(self.savePathConfig, DPS_PathSelector, self.configfolderpath[1].value, "config")

		elif cur == self.playerTempPath:
			self.session.openWithCallback(self.savePathConfig, DPS_PathSelector, self.playerTempPath[1].value, "player")

		elif cur == self.logfolderpath:
			self.session.openWithCallback(self.savePathConfig, DPS_PathSelector, self.logfolderpath[1].value, "log")

		elif cur == self.cachefolderpath:
			self.session.openWithCallback(self.savePathConfig, DPS_PathSelector, self.cachefolderpath[1].value, "cache")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def savePathConfig(self, pathValue, myType):
		printl("", self, "S")

		printl("pathValue: " + str(pathValue), self, "D")
		printl("type: " + str(myType), self, "D")

		if pathValue is not None:
			settings: SettingsStorage = Singleton().getSettingsInstance()

			if myType == "media":
				settings.mediaFolderPath.setValue(pathValue)

			elif myType == "config":
				settings.configFolderPath.setValue(pathValue)

			elif myType == "player":
				settings.playerTempPath.setValue(pathValue)

			elif myType == "log":
				settings.logFolderPath.setValue(pathValue)

			elif myType == "cache":
				settings.cacheFolderPath.setValue(pathValue)

			settings.writeToFile()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keySave(self):
		printl("", self, "S")

		settings: SettingsStorage = Singleton().getSettingsInstance()
		settings.writeToFile()

		if settings.skinName.getValue() != self._skinNameAtOpen:
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(lambda _result=None: self.close(None), MessageBox,
				_("The skin was changed. Exit and re-enter DreamPlex to apply it."),
				MessageBox.TYPE_INFO, timeout=6)
		else:
			self.close(None)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyLeft(self):
		printl("", self, "S")

		ConfigListScreen.keyLeft(self)
		self.createSetup()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyRight(self):
		printl("", self, "S")

		ConfigListScreen.keyRight(self)
		self.createSetup()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyBouquetUp(self):
		printl("", self, "S")

		self["config"].instance.moveSelection(self["config"].instance.pageUp)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyBouquetDown(self):
		printl("", self, "S")

		self["config"].instance.moveSelection(self["config"].instance.pageDown)

		printl("", self, "C")
