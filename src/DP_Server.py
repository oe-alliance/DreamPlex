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
import time

from enigma import eTimer

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.Sources.List import List
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import config, getConfigListEntry, configfile
from Components.Input import Input

from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.InputBox import InputBox
from Screens.Screen import Screen

from .__common__ import printl2 as printl
from .__init__ import initServerEntryConfig, _  # _ is translation

from .DP_PlexLibrary import PlexLibrary
from .DP_Mappings import DPS_Mappings
from .DP_Users import DPS_Users
from .DP_Syncer import DPS_Syncer
from .DPH_PlexGdm import PlexGdm
from .DPH_ScreenHelper import DPH_PlexScreen
from .DP_ViewFactory import getGuiElements
from .DPH_Singleton import Singleton
#===============================================================================
#
#===============================================================================


# how many one-second polls to wait for the GDM search before giving up, so a
# silent network cannot leave the timer running for ever
GDM_MAX_ATTEMPTS = 10


class DPS_Server(Screen, DPH_PlexScreen):

	gdmTimer = None
	gdmClient = None
	gdmAttempts = 0

	def __init__(self, session, what=None):
		printl("", self, "S")

		Screen.__init__(self, session)
		DPH_PlexScreen.__init__(self)

		self.guiElements = getGuiElements()

		self["Title"] = Label(_("System Server"))

		self["entryList"] = List(self.builEntryList(), True)
		self["header"] = Label()
		self["columnHeader"] = Label()

		self["btn_redText"] = Label()
		self["btn_red"] = Pixmap()

		self["btn_greenText"] = Label()
		self["btn_green"] = Pixmap()

		self["btn_yellowText"] = Label()
		self["btn_yellow"] = Pixmap()

		self["btn_blueText"] = Label()
		self["btn_blue"] = Pixmap()

		self["actions"] = ActionMap(["WizardActions", "MenuActions", "ShortcutActions"],
			{
			 "ok": self.keyOk,
			 "back": self.keyClose,
			 "red": self.keyRed,
			 "yellow": self.keyYellow,
			 "green": self.keyGreen,
			 "blue": self.keyBlue,
			 }, -1)
		self.what = what

		self.onLayoutFinish.append(self.finishLayout)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def finishLayout(self):
		printl("", self, "S")

		# first we set the pics for buttons
		self.setColorFunctionIcons()

		self["header"].setText(_("Server List:"))

		if self.skinResolution == "FHD":  # FHD is used for FULL HD Boxes with new framebuffer
			self["columnHeader"].setText(_("Name                                         IP/plex.tv                                            Port/Email                                        Active"))
		else:
			self["columnHeader"].setText(_("Name                                         IP/plex.tv                                 Port/Email                                  Active"))

		self["btn_redText"].setText(_("Delete"))
		self["btn_greenText"].setText(_("Add"))
		self["btn_yellowText"].setText(_("Sync Media"))
		self["btn_blueText"].setText(_("Discover"))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def builEntryList(self):
		printl("", self, "S")

		self.myEntryList = []

		for serverConfig in config.plugins.dreamplex.Entries:

			name = serverConfig.name.value

			if serverConfig.connectionType.value == "2":
				text1 = serverConfig.myplexUrl.value
				text2 = serverConfig.myplexUsername.value
			else:
				text1 = "%d.%d.%d.%d" % tuple(serverConfig.ip.value)
				text2 = "%d" % serverConfig.port.value

			active = str(serverConfig.state.value)

			self.myEntryList.append((name, text1, text2, active, serverConfig))

		printl("", self, "C")
		return self.myEntryList

	#===========================================================================
	#
	#===========================================================================
	def updateList(self):
		printl("", self, "S")

		self["entryList"].setList(self.builEntryList())

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyClose(self):
		printl("", self, "S")

		self.close(self.session, self.what, None)

		printl("", self, "C")

	#=======================================================================
	#
	#=======================================================================
	def keyGreen(self):
		printl("", self, "S")

		self.session.openWithCallback(self.updateList, DPS_ServerConfig, None)

		printl("", self, "C")

	#=======================================================================
	#
	#=======================================================================
	def keyRed(self):
		printl("", self, "S")

		try:
			sel = self["entryList"].getCurrent()[4]

		except Exception as ex:
			printl("Exception: " + str(ex), self, "W")
			sel = None

		if sel is None:
			return

		self.session.openWithCallback(self.deleteConfirm, MessageBox, _("Really delete this Server Entry?"))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def useSelectedServerData(self, choice):
		printl("", self, "S")

		if choice is not None:
			serverData = choice[1]
			self.session.openWithCallback(self.updateList, DPS_ServerConfig, None, serverData)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyOk(self):
		printl("", self, "S")

		try:
			sel = self["entryList"].getCurrent()[4]

		except Exception as ex:
			printl("Exception: " + str(ex), self, "W")
			sel = None

		if sel is None:
			return

		printl("config selction: " + str(sel), self, "D")
		self.session.openWithCallback(self.updateList, DPS_ServerConfig, sel)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyYellow(self):
		printl("", self, "S")

		try:
			serverConfig = self["entryList"].getCurrent()[4]

		except Exception as ex:
			printl("Exception: " + str(ex), self, "W")
			serverConfig = None

		if serverConfig is None:
			return

		printl("config selction: " + str(serverConfig), self, "D")
		self.session.open(DPS_Syncer, "sync", serverConfig)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyBlue(self):
		"""Discover servers on the LAN without freezing the GUI.

		This is an ActionMap callback, so it runs on the enigma2 main loop.
		It used to sit in a `while not discovery_complete: sleep(1)` loop,
		which blocks everything until the answer arrives - and forever if it
		never does. The wait is now a timer, with a cap so a silent GDM
		cannot leave it spinning.
		"""
		printl("", self, "S")

		self.gdmClient = PlexGdm()
		self.gdmClient.setClientDetails()
		self.gdmClient.start_discovery()

		self.gdmAttempts = 0

		# reuse the timer object rather than replacing a live one
		if self.gdmTimer is None:
			self.gdmTimer = eTimer()
			self.gdmTimer.callback.append(self.checkDiscovery)

		self.gdmTimer.start(1000, False)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def checkDiscovery(self):
		printl("", self, "S")

		self.gdmAttempts += 1

		if not self.gdmClient.discovery_complete and self.gdmAttempts < GDM_MAX_ATTEMPTS:
			printl("waiting for results (%s/%s)" % (self.gdmAttempts, GDM_MAX_ATTEMPTS), self, "D")
			printl("", self, "C")
			return

		if self.gdmTimer is not None:
			self.gdmTimer.stop()

		timedOut = not self.gdmClient.discovery_complete
		self.gdmClient.stop_discovery()

		serverList = self.gdmClient.getServerList()
		printl("serverList: " + str(serverList), self, "D")

		if timedOut and not serverList:
			printl("discovery timed out with nothing found", self, "W")
			self.session.open(MessageBox, _("No server answered the search."), MessageBox.TYPE_INFO, timeout=5)
			printl("", self, "C")
			return

		menu = []
		for server in serverList:
			printl("server: " + str(server), self, "D")
			menu.append((str(server.get("serverName")) + " (" + str(server.get("server")) + ":" + str(server.get("port")) + ")", server,))

		printl("menu: " + str(menu), self, "D")
		self.session.openWithCallback(self.useSelectedServerData, ChoiceBox, title=_("Select server"), list=menu)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def deleteConfirm(self, result):
		printl("", self, "S")

		if not result:
			return

		sel = self["entryList"].getCurrent()[4]
		config.plugins.dreamplex.entriescount.value -= 1
		config.plugins.dreamplex.entriescount.save()
		config.plugins.dreamplex.Entries.remove(sel)
		config.plugins.dreamplex.Entries.save()
		config.plugins.dreamplex.save()
		configfile.save()
		self.updateList()

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPS_ServerConfig(ConfigListScreen, Screen, DPH_PlexScreen):

	useMappings = False
	useHomeUsers = False
	authenticated = False

	def __init__(self, session, entry, data=None):
		printl("", self, "S")

		Screen.__init__(self, session)

		self.guiElements = getGuiElements()

		self["actions"] = ActionMap(["DPS_ServerConfig", "ColorActions"],
		{
			"green": self.keySave,
			"cancel": self.keyCancel,
		    "exit": self.keyCancel,
			"yellow": self.keyYellow,
			"blue": self.keyBlue,
			"red": self.keyRed,
			"left": self.keyLeft,
			"right": self.keyRight,
		}, -2)

		self["help"] = StaticText()

		self["Title"] = Label(_("Server Config"))

		self["btn_redText"] = Label()
		self["btn_red"] = Pixmap()

		self["btn_greenText"] = Label()
		self["btn_green"] = Pixmap()

		self["btn_yellowText"] = Label()
		self["btn_yellow"] = Pixmap()

		self["btn_blueText"] = Label()
		self["btn_blue"] = Pixmap()

		if entry is None:
			self.newmode = 1
			self.current = initServerEntryConfig()
			if data is not None:
				ipBlocks = data.get("server").split(".")
				self.current.name.value = data.get("serverName")
				self.current.ip.value = [int(ipBlocks[0]), int(ipBlocks[1]), int(ipBlocks[2]), int(ipBlocks[3])]
				self.current.port.value = int(data.get("port"))

		else:
			self.newmode = 0
			self.current = entry
			self.currentId = self.current.id.value
			printl("currentId: " + str(self.currentId), self, "D")

		self.cfglist = []
		ConfigListScreen.__init__(self, self.cfglist, session)

		self["config"].onSelectionChanged.append(self.updateHelp)

		self.onLayoutFinish.append(self.finishLayout)

		self.onShown.append(self.checkForPinUsage)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def finishLayout(self):
		printl("", self, "S")
		print("here")

		# first we set the pics for buttons
		self.setColorFunctionIcons()

		self.setKeyNames()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def checkForPinUsage(self):
		printl("", self, "S")

		self.onShown = []

		if not self.authenticated:
			if self.current.protectSettings.value:
				self.session.openWithCallback(self.askForPin, InputBox, title=_("Please enter the pincode!"), type=Input.PIN)
			else:
				self.authenticated = True
				self.createSetup()
		else:
			self.createSetup()

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def askForPin(self, enteredPin):
		printl("", self, "S")

		if enteredPin is None:
			pass
		else:
			if int(enteredPin) == int(self.current.settingsPin.value):
				#self.session.open(MessageBox,"The pin was correct!", MessageBox.TYPE_INFO)
				self.authenticated = True
				self.createSetup()
			else:
				self.session.open(MessageBox, "The pin was wrong! Returning ...", MessageBox.TYPE_INFO)
				self.close()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def createSetup(self):
		printl("", self, "S")

		separator = "".ljust(250, "_")

		self.cfglist = []
		##
		self.cfglist.append(getConfigListEntry(_("General Settings ") + separator, config.plugins.dreamplex.about, _("-")))
		##
		self.cfglist.append(getConfigListEntry(_(" > State"), self.current.state, _("Toggle state to on/off to show this server in the list or not.")))
		self.cfglist.append(getConfigListEntry(_(" > Autostart"), self.current.autostart, _("Enter this server automatically on startup.")))
		self.cfglist.append(getConfigListEntry(_(" > Name"), self.current.name, _("Simply a name for better overview")))
		self.cfglist.append(getConfigListEntry(_(" > Trailer"), self.current.loadExtraData, _("Enable trailer function. Only works with PlexPass or YYTrailer plugin.")))

		##
		self.cfglist.append(getConfigListEntry(_("Connection Settings ") + separator, config.plugins.dreamplex.about, _(" ")))
		##
		self.cfglist.append(getConfigListEntry(_(" > Connection Type"), self.current.connectionType, _("Select your type how the box is reachable.")))

		if self.current.connectionType.value == "0" or self.current.connectionType.value == "1":  # IP or DNS
			self.cfglist.append(getConfigListEntry(_(" > Local Authentication"), self.current.localAuth, _("Use this if you secured your plex server in the settings.")))
			if self.current.connectionType.value == "0":
				self.addIpSettings()
			else:
				self.cfglist.append(getConfigListEntry(_(" >> DNS"), self.current.dns, _(" ")))
				self.cfglist.append(getConfigListEntry(_(" >> Port"), self.current.port, _(" ")))
			if getattr(self.current, "accessToken", None) is not None:
				self.cfglist.append(getConfigListEntry(_(" > Access Token (optional)"), self.current.accessToken, _("X-Plex-Token used to authenticate against this server. Overrides local authentication and plex.tv tokens.")))
			if self.current.localAuth.value:
				self.addMyPlexSettings()

		elif self.current.connectionType.value == "2":  # plex.tv
			self.addMyPlexSettings()

		##
		self.cfglist.append(getConfigListEntry(_("Playback Settings ") + separator, config.plugins.dreamplex.about, _(" ")))
		##

		self.cfglist.append(getConfigListEntry(_(" > Playback Type"), self.current.playbackType, _(" ")))
		if self.current.playbackType.value == "0":
			self.useMappings = False

		elif self.current.playbackType.value == "1":
			self.useMappings = False
			self.cfglist.append(getConfigListEntry(_(" >> Use universal Transcoder"), self.current.universalTranscoder, _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
			if not self.current.universalTranscoder.value:
				self.cfglist.append(getConfigListEntry(_(" >> Transcoding quality"), self.current.quality, _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
				self.cfglist.append(getConfigListEntry(_(" >> Segmentsize in seconds"), self.current.segments, _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
			else:
				self.cfglist.append(getConfigListEntry(_(" >> Transcoding video codec"), self.current.transcodeVideoCodec, _("H.264 works everywhere. HEVC/H.265 halves the bitrate but the server must be Plex Pass with hardware encoding enabled ('Enable HEVC video encoding' in Transcoder settings, not available on AMD) - if it cannot, the server silently falls back to H.264.")))
				# each codec has its own ladder, so only the one in use is shown
				if self.current.transcodeVideoCodec.value == "hevc":
					self.cfglist.append(getConfigListEntry(_(" >> Transcoding quality"), self.current.uniQualityHevc, _("Same bitrates as H.264 but a bigger picture at every step, because HEVC needs clearly less bitrate for the same quality. 1440p and 2160p ask a lot from the server and only pay off with a source of that resolution.")))
				else:
					self.cfglist.append(getConfigListEntry(_(" >> Transcoding quality"), self.current.uniQuality, _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))

		elif self.current.playbackType.value == "2":
			self.useMappings = True
			self.cfglist.append(getConfigListEntry(_("> Search and use forced subtitles"), self.current.useForcedSubtitles, _("Monitor playback to activate subtitles automatically if needed. You have to enable subtitles with the 'Text' button first.")))

		elif self.current.playbackType.value == "3":
			self.useMappings = False
			#self.cfglist.append(getConfigListEntry(_(">> Username"), self.current.smbUser))
			#self.cfglist.append(getConfigListEntry(_(">> Password"), self.current.smbPassword))
			#self.cfglist.append(getConfigListEntry(_(">> Server override IP"), self.current.nasOverrideIp))
			#self.cfglist.append(getConfigListEntry(_(">> Servers root"), self.current.nasRoot))

		if self.current.playbackType.value == "2":
			##
			self.cfglist.append(getConfigListEntry(_("Subtitle Settings ") + separator, config.plugins.dreamplex.about, _(" ")))
			##
			self.cfglist.append(getConfigListEntry(_(" >> Enable Subtitle renaming in direct local mode"), self.current.srtRenamingForDirectLocal, _("Renames filename.eng.srt automatically to filename.srt so e2 is able to read them.")))
			if self.current.srtRenamingForDirectLocal.value:
				self.cfglist.append(getConfigListEntry(_(" >> Target subtitle language"), self.current.subtitlesLanguage, _("Search string that should be removed from srt file.")))

		##
		self.cfglist.append(getConfigListEntry(_("Wake On Lan Settings ") + separator, config.plugins.dreamplex.about, _(" ")))
		##
		self.cfglist.append(getConfigListEntry(_(" > Use Wake on Lan (WoL)"), self.current.wol, _(" ")))

		if self.current.wol.value:
			self.cfglist.append(getConfigListEntry(_(" >> Mac address (Size: 12 alphanumeric no seperator) only for WoL"), self.current.wol_mac, _(" ")))
			self.cfglist.append(getConfigListEntry(_(" >> Wait for server delay (max 180 seconds) only for WoL"), self.current.wol_delay, _(" ")))

		##
		self.cfglist.append(getConfigListEntry(_("Sync Settings ") + separator, config.plugins.dreamplex.about, _(" ")))
		##
		self.cfglist.append(getConfigListEntry(_(" > Sync Movies Medias"), self.current.syncMovies, _("Sync this content.")))
		self.cfglist.append(getConfigListEntry(_(" > Sync Shows Medias"), self.current.syncShows, _("Sync this content.")))
		self.cfglist.append(getConfigListEntry(_(" > Sync Music Medias"), self.current.syncMusic, _("Sync this content.")))

		self["config"].list = self.cfglist
		self["config"].l.setList(self.cfglist)

		if self.current.myplexHomeUsers.value:
			self.useHomeUsers = True
		else:
			self.useHomeUsers = False

		self.setKeyNames()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def addIpSettings(self):
		printl("", self, "S")

		self.cfglist.append(getConfigListEntry(_(" >> IP"), self.current.ip, _(" ")))
		self.cfglist.append(getConfigListEntry(_(" >> Port"), self.current.port, _(" ")))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def addMyPlexSettings(self):
		printl("", self, "S")

		self.cfglist.append(getConfigListEntry(_(" >> plex.tv URL"), self.current.myplexUrl, ''))
		self.cfglist.append(getConfigListEntry(_(" >> plex.tv Username"), self.current.myplexUsername, ''))
		self.cfglist.append(getConfigListEntry(_(" >> plex.tv Password"), self.current.myplexPassword, ''))
		self.cfglist.append(getConfigListEntry(_(" >> plex.tv Token"), self.current.myplexToken, _("Filled in automatically after a successful login. You can also paste a token here to use one issued elsewhere - leave it empty to force a fresh login with the username and password above.")))

		self.cfglist.append(getConfigListEntry(_(" >> plex.tv Home Users"), self.current.myplexHomeUsers, _("Use Home Users?")))
		if self.current.myplexHomeUsers.value:
			self.cfglist.append(getConfigListEntry(_(" >> Use Settings Protection"), self.current.protectSettings, _("Ask for pin?")))
			if self.current.protectSettings.value:
				self.cfglist.append(getConfigListEntry(_(" >> Settings Pincode"), self.current.settingsPin, _("Pincode for changing settings")))

			self.cfglist.append(getConfigListEntry(_(" >> plex.tv Pin Protection"), self.current.myplexPinProtect, _("Use Pinprotection for switch back to plex.tv user?")))
			if self.current.myplexPinProtect.value:
				self.cfglist.append(getConfigListEntry(_(" >> plex.tv Pincode"), self.current.myplexPin, _("Pincode for switching back from any home user.")))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def updateHelp(self):
		printl("", self, "S")

		cur = self["config"].getCurrent()
		printl("cur: " + str(cur), self, "D")
		self["help"].setText(cur[2])  # = cur and cur[2] or ""

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setKeyNames(self):
		printl("", self, "S")

		self["btn_greenText"].setText(_("Save"))

		if self.useMappings and self.newmode == 0:
			self["btn_yellowText"].setText(_("Mappings"))
			self["btn_yellowText"].show()
			self["btn_yellow"].show()
		elif self.current.localAuth.value:
			self["btn_yellowText"].setText(_("get local auth Token"))
			self["btn_yellowText"].show()
			self["btn_yellow"].show()
		else:
			self["btn_yellowText"].hide()
			self["btn_yellow"].hide()

		if (self.current.localAuth.value or self.current.connectionType.value == "2") and self.newmode == 0:
			if self.useHomeUsers:
				self["btn_redText"].setText(_("Home Users"))
				self["btn_redText"].show()
				self["btn_red"].show()
			else:
				self["btn_redText"].hide()
				self["btn_red"].hide()

			self["btn_blueText"].setText(_("(re)create plex.tv Token"))

			self["btn_blueText"].show()
			self["btn_blue"].show()
		else:
			self["btn_redText"].hide()
			self["btn_red"].hide()
			self["btn_blueText"].hide()
			self["btn_blue"].hide()

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
	def keySave(self):
		printl("", self, "S")

		if self.newmode == 1:
			config.plugins.dreamplex.entriescount.value += 1
			config.plugins.dreamplex.entriescount.save()

		#if self.current.machineIdentifier.value == "":
		from .DP_PlexLibrary import PlexLibrary
		self.plexInstance = Singleton().getPlexInstance(PlexLibrary(self.session, self.current))

		machineIdentifiers = ""

		if self.current.connectionType.value == "2":
			xmlResponse = self.plexInstance.getSharedServerForPlexUser()
			machineIdentifier = xmlResponse.get("machineIdentifier")
			if machineIdentifier is not None:
				machineIdentifiers += machineIdentifier

			servers = xmlResponse.findall("Server")
			for server in servers:
				machineIdentifier = server.get("machineIdentifier")
				if machineIdentifier is not None:
					machineIdentifiers += ", " + machineIdentifier

		else:
			http = self.plexInstance.http
			url = "%s://%s:%s" % (http, str(self.plexInstance.g_host), str(self.plexInstance.serverConfig_port))
			xmlResponse = self.plexInstance.getXmlTreeFromUrl(url)
			machineIdentifier = xmlResponse.get("machineIdentifier")

			if machineIdentifier is not None:
				machineIdentifiers += xmlResponse.get("machineIdentifier")

		self.current.machineIdentifier.value = machineIdentifiers
		printl("machineIdentifier: " + str(self.current.machineIdentifier.value), self, "D")

		# Only sign in to plex.tv when there is no token yet. Re-authenticating
		# on every save breaks servers provisioned with a token but no stored
		# password (the token is what runtime uses anyway - see
		# setMyPlexData), turning any edit into "Invalid email, username, or
		# password". Clear the token field to force a fresh login.
		needsToken = (self.current.connectionType.value == "2" or self.current.localAuth.value) \
					and not self.current.myplexToken.value

		if needsToken:
			self.keyBlue()
		else:
			self.saveNow()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def saveNow(self, retval=None):
		printl("", self, "S")

		config.plugins.dreamplex.entriescount.save()
		config.plugins.dreamplex.Entries.save()
		config.plugins.dreamplex.save()
		configfile.save()

		self.close()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyCancel(self):
		printl("", self, "S")

		if self.newmode == 1:
			config.plugins.dreamplex.Entries.remove(self.current)
		ConfigListScreen.cancelConfirm(self, True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyYellow(self):
		printl("", self, "S")

		if self.useMappings:
			serverID = self.currentId
			self.plexInstance = Singleton().getPlexInstance(PlexLibrary(self.session, self.current))
			serverpaths = self.plexInstance.getServerSectionPaths()
			self.session.open(DPS_Mappings, serverID, serverpaths)

		elif self.current.localAuth.value:
			# now that we know the server we establish global plexInstance
			self.plexInstance = Singleton().getPlexInstance(PlexLibrary(self.session, self.current))

			ipInConfig = "%d.%d.%d.%d" % tuple(self.current.ip.value)
			token = self.plexInstance.getPlexUserTokenForLocalServerAuthentication(ipInConfig)

			if token:
				self.current.myplexLocalToken.value = token
				self.current.myplexLocalToken.save()
				self.session.open(MessageBox, (_("Local Token:") + "\n%s \n" + _("for the user:") + "\n%s") % (token, self.current.myplexTokenUsername.value), MessageBox.TYPE_INFO)
			else:
				response = self.plexInstance.getLastResponse()
				self.session.open(MessageBox, (_("Error:") + "\n%s \n" + _("for the user:") + "\n%s") % (response, self.current.myplexTokenUsername.value), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyBlue(self):
		printl("", self, "S")

		# now that we know the server we establish global plexInstance
		self.plexInstance = Singleton().getPlexInstance(PlexLibrary(self.session, self.current))

		token = self.plexInstance.getNewMyPlexToken()

		if token:
			self.session.openWithCallback(self.saveNow, MessageBox, (_("plex.tv Token:") + "\n%s \n" + _("for the user:") + "\n%s \n" + _("with the id:") + "\n%s") % (token, self.current.myplexTokenUsername.value, self.current.myplexId.value), MessageBox.TYPE_INFO)
		else:
			response = self.plexInstance.getLastResponse()
			self.session.openWithCallback(self.saveNow, MessageBox, (_("Error:") + "\n%s \n" + _("for the user:") + "\n%s") % (response, self.current.myplexTokenUsername.value), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyRed(self):
		printl("", self, "S")

		if self.useHomeUsers:
			serverID = self.currentId
			plexInstance = Singleton().getPlexInstance(PlexLibrary(self.session, self.current))
			self.session.open(DPS_Users, serverID, plexInstance)

		#self.session.open(MessageBox,(_("plex.tv Token:") + "\n%s \n" + _("plex.tv Localtoken:") + "\n%s \n"+ _("for the user:") + "\n%s") % (self.current.myplexToken.value, self.current.myplexLocalToken.value, self.current.myplexTokenUsername.value), MessageBox.TYPE_INFO)

		printl("", self, "C")
