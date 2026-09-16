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
from __future__ import annotations
from typing import Any
import time

from enigma import eTimer

from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.Sources.List import List
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import ConfigElement, ConfigSelection, ConfigIP, ConfigInteger, ConfigText, getConfigListEntry
from Components.Input import Input

from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.InputBox import InputBox
from Screens.Screen import Screen
from .DP_HelperScreens import DPS_TextInputBox
from . import ServerSettings, ServerSettingsData, AbstractServerSettings, EMPTY_SERVER_CONF
from .DP_SettingsStorage import SettingsStorage, BaseSettings, T, AuthorizationMode, AuthorizationResult, USER_SWITCH_NONE

from .__common__ import printl2 as printl, DiscoveredServer, EntryServer
from . import _  # _ is translation

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

def _copyServerFields(source: AbstractServerSettings, dest: AbstractServerSettings) -> None:
	# Identity/authentication material a "clone this server for another
	# user" action must NOT carry over - each backend declares its own
	# private field names via getCloneExcludeFields() (see PlexSettings/
	# JellyfinSettings) rather than this function knowing them by server
	# type. Everything else (connection, playback, subtitle/audio prefs,
	# ...) is copied as-is: the whole point of cloning is to skip
	# re-entering all of that for a second login on the same physical server.
	exclude = source.getCloneExcludeFields()
	for attrName, attrValue in vars(source).items():
		if attrName in exclude or not isinstance(attrValue, BaseSettings):
			continue
		destAttr = getattr(dest, attrName, None)
		if isinstance(destAttr, BaseSettings):
			try:
				destAttr.setValue(attrValue.getValue())
			except Exception as ex:
				printl("could not clone field " + attrName + ": " + str(ex), "DP_Server", "W")


class DPS_Server(Screen, DPH_PlexScreen):

	def __init__(self, session, what=None):
		printl("", self, "S")

		Screen.__init__(self, session)
		DPH_PlexScreen.__init__(self)

		self.guiElements = getGuiElements()

		self["Title"] = Label(_("System Server"))

		self["entryList"] = List(self.buildEntryList(), True)
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

		# MENU has no colored icon on most remotes, so unlike the four
		# btn_*/btn_*Text pairs above this is text-only, placed on its own row
		# in the skin rather than squeezed into the colored-button bar.
		self["btn_menuText"] = Label()

		self["actions"] = ActionMap(["WizardActions", "MenuActions", "ShortcutActions"],
									{
										"ok": self.keyOk,
										"back": self.keyClose,
										"red": self.keyRed,
										"yellow": self.keyYellow,
										"green": self.keyGreen,
										"blue": self.keyBlue,
										"menu": self.keyMenu,
									}, -1)
		self.what = what
		# Parameters for the custom Jellyfin discovery
		from .DPH_JellyfinDiscovery import JELLYFIN_HTTP_PORT
		self._jd_params = { 'base': None, 'start': 1, 'end': 254, 'timeout': 0.5, 'port': JELLYFIN_HTTP_PORT }

		# State of the asynchronous discovery (see _startDiscovery)
		self._discoveryClient = None
		self._discoveryTimer = None
		self._discoveryDeadline = 0.0

		self.onLayoutFinish.append(self.finishLayout)
		self.onClose.append(self._stopDiscovery)

		printl("", self, "C")

	# ===========================================================================
	#
	# ===========================================================================
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
		self["btn_menuText"].setText(_("MENU: Clone for another user"))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def buildEntryList(self) -> list[tuple]:
		printl("", self, "S")

		# The skin's "entryList" widget is rendered by TemplatedMultiContent
		# (text = 0/1/2/3), which the native eListboxPythonMultiContent reads
		# with direct tuple access - a plain indexable object (e.g. the
		# EntryServer dataclass) is not enough, it renders as an empty list
		# on a real box with no error. The EntryServer is kept as the 5th
		# element for keyOk/keyRed/keyYellow/deleteConfirm, which need
		# entry.settings.
		self.myEntryList: list[tuple] = []
		settings: SettingsStorage = Singleton().getSettingsInstance()

		for serverConfig in settings.serverConfigs:
			entry: EntryServer = serverConfig.toEntryServer()

			self.myEntryList.append((entry.name, entry.serverHost, entry.serverPort, entry.active, entry))

		printl("", self, "C")
		return self.myEntryList

	#===========================================================================
	#
	#===========================================================================
	def updateList(self):
		printl("", self, "S")

		self["entryList"].setList(self.buildEntryList())

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
			entry: EntryServer = self["entryList"].getCurrent()[4]
			sel = entry.settings

		except Exception as ex:
			printl("Exception: " + str(ex), self, "W")
			sel = None

		if sel is None:
			return

		self.session.openWithCallback(self.deleteConfirm, MessageBox, _("Really delete this Server Entry?"))

		printl("", self, "C")

	#===========================================================================
	# MENU key on a server entry: clone its settings (everything but
	# username/password/token) into a new server entry, so a second login on
	# the same server does not need the connection/playback/subtitle prefs
	# re-entered from scratch. Available for any real, configured server
	# (i.e. anything other than the EMPTY_SERVER_CONF placeholder row).
	#===========================================================================
	def keyMenu(self):
		printl("", self, "S")

		try:
			entry: EntryServer = self["entryList"].getCurrent()[4]
			sel = entry.settings
		except Exception as ex:
			printl("Exception: " + str(ex), self, "W")
			sel = None

		if sel is None or sel.getType() == EMPTY_SERVER_CONF:
			printl("", self, "C")
			return

		self._pendingCloneSource = sel
		self.session.openWithCallback(self._onCloneConfirm, MessageBox,
			_("Clone this server's settings into a new server entry?\nYou will be asked for a username/password for the new one."), MessageBox.TYPE_YESNO)

		printl("", self, "C")

	def _onCloneConfirm(self, answer):
		printl("", self, "S")

		sel = getattr(self, "_pendingCloneSource", None)
		self._pendingCloneSource = None

		if not answer or sel is None:
			printl("", self, "C")
			return

		self.session.openWithCallback(self.updateList, DPS_ServerConfig, None, None, sel)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def useSelectedServerData(self, choice):
		printl("", self, "S")

		if choice is not None:
			serverData: DiscoveredServer = choice[1]
			self.session.openWithCallback(self.updateList, DPS_ServerConfig, None, serverData)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyOk(self):
		printl("", self, "S")

		try:
			sel: EntryServer = self["entryList"].getCurrent()[4]

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
			entry: EntryServer = self["entryList"].getCurrent()[4]
			serverConfig = entry.settings

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
		printl("", self, "S")

		# Ask which discovery to run
		choices = [
			(_("Discover Plex"), "plex"),
			(_("Discover Jellyfin"), "jellyfin"),
		]
		self.session.openWithCallback(self._onDiscoveryChoice, ChoiceBox, title=_("Select discovery"), list=choices)

		printl("", self, "C")

	def _onDiscoveryChoice(self, choice):
		if not choice:
			return
		label, kind = choice
		if kind == "plex":
			self._runPlexDiscovery()
		else:
			self._runJellyfinDiscovery()

	#===========================================================================
	# Asynchronous discovery
	#
	# Both PlexGdm and JellyfinDiscovery run the scan in a worker thread and
	# expose discovery_complete / getServerList(). Here we follow their
	# progress with an eTimer: waiting in a time.sleep() loop would block the
	# enigma2 main loop, freezing the whole box for the entire duration of the
	# scan.
	#===========================================================================
	DISCOVERY_POLL_INTERVAL = 200   # ms between one check and the next
	DISCOVERY_TIMEOUT = 120         # seconds after which we give up

	def _startDiscovery(self, client):
		printl("", self, "S")

		self._stopDiscovery()

		self._discoveryClient = client
		self._discoveryDeadline = time.time() + self.DISCOVERY_TIMEOUT

		client.start_discovery()

		self._discoveryTimer = eTimer()
		self._discoveryTimer.callback.append(self._pollDiscovery)
		self._discoveryTimer.start(self.DISCOVERY_POLL_INTERVAL, False)

		printl("", self, "C")

	def _pollDiscovery(self):
		client = self._discoveryClient
		if client is None:
			return

		if not client.discovery_complete and time.time() < self._discoveryDeadline:
			return

		timedOut = not client.discovery_complete
		if timedOut:
			printl("discovery timed out", self, "W")

		serverList: list[DiscoveredServer] = client.getServerList()
		self._stopDiscovery()
		self._showDiscoveryResults(serverList)

	def _stopDiscovery(self):
		if self._discoveryTimer is not None:
			self._discoveryTimer.stop()
			self._discoveryTimer = None

		if self._discoveryClient is not None:
			client, self._discoveryClient = self._discoveryClient, None
			try:
				client.stop_discovery()
			except Exception as ex:
				printl("exception: " + str(ex), self, "W")

	def _runPlexDiscovery(self):
		client = PlexGdm()
		client.setClientDetails()
		self._startDiscovery(client)

	def _runJellyfinDiscovery(self):
		from .DPH_JellyfinDiscovery import JellyfinDiscovery, JELLYFIN_HTTP_PORT
		# Ask whether to run a quick or a custom scan
		choices = [
			(_("Quick scan (/24)"), "quick"),
			(_("Custom scan…"), "custom"),
		]
		def _after_choice(choice):
			if not choice:
				return
			label, kind = choice
			if kind == "custom":
				# Start the parameter wizard
				self._jd_params = { 'base': None, 'start': 1, 'end': 254, 'timeout': 0.5, 'port': JELLYFIN_HTTP_PORT }
				self._askJDBase()
			else:
				self._startDiscovery(JellyfinDiscovery(timeout=0.3))
		self.session.openWithCallback(_after_choice, ChoiceBox, title=_("Jellyfin discovery"), list=choices)

	# Custom Jellyfin discovery wizard
	def _confirmAbortJDWizard(self, retry):
		# ESC on a DPS_TextInputBox closes it with value=None (cancel()),
		# indistinguishable from confirming an empty field - without this,
		# every step's "if value: ..." just silently kept its default and
		# moved on to the next question instead of stopping, so ESC never
		# actually interrupted the wizard.
		def _onAnswer(reallyAbort):
			if not reallyAbort:
				retry()
		self.session.openWithCallback(_onAnswer, MessageBox, _("Interrupt the Jellyfin server search?"), MessageBox.TYPE_YESNO)

	def _askJDBase(self, value=None):
		if value is not None:
			self._jd_params['base'] = value
		title = _("Enter subnet base (e.g. 192.168.1)")
		self.session.openWithCallback(self._askJDStart, DPS_TextInputBox, title=title, type=Input.TEXT)

	def _askJDStart(self, base):
		if base is None:
			self._confirmAbortJDWizard(self._askJDBase)
			return
		if base:
			self._jd_params['base'] = base
		title = _("Start host (1-254)")
		self.session.openWithCallback(self._askJDEnd, DPS_TextInputBox, title=title, type=Input.TEXT)

	def _askJDEnd(self, start):
		if start is None:
			self._confirmAbortJDWizard(self._askJDStart)
			return
		if start and start.isdigit():
			self._jd_params['start'] = int(start)
		title = _("End host (1-254)")
		self.session.openWithCallback(self._askJDTimeout, DPS_TextInputBox, title=title, type=Input.TEXT)

	def _askJDTimeout(self, end):
		if end is None:
			self._confirmAbortJDWizard(self._askJDEnd)
			return
		if end and end.isdigit():
			self._jd_params['end'] = int(end)
		title = _("Timeout seconds (e.g. 0.5)")
		self.session.openWithCallback(self._askJDPort, DPS_TextInputBox, title=title, type=Input.TEXT)

	def _askJDPort(self, timeout):
		if timeout is None:
			self._confirmAbortJDWizard(self._askJDTimeout)
			return
		try:
			if timeout:
				self._jd_params['timeout'] = float(timeout)
		except Exception:
			pass
		from .DPH_JellyfinDiscovery import JELLYFIN_HTTP_PORT
		title = _("Jellyfin port (default %d)") % JELLYFIN_HTTP_PORT
		self.session.openWithCallback(self._runJDScan, DPS_TextInputBox, title=title, type=Input.TEXT, text=str(self._jd_params.get('port', JELLYFIN_HTTP_PORT)))

	def _runJDScan(self, port):
		if port is None:
			self._confirmAbortJDWizard(self._askJDPort)
			return
		from .DPH_JellyfinDiscovery import JellyfinDiscovery
		port = str(port).strip() if port else ""
		if port.isdigit():
			self._jd_params['port'] = int(port)
		jd = JellyfinDiscovery(timeout=self._jd_params.get('timeout', 0.5))
		jd.set_params(subnet_base=self._jd_params.get('base'), start=self._jd_params.get('start', 1), end=self._jd_params.get('end', 254), timeout=self._jd_params.get('timeout', 0.5), port=self._jd_params.get('port'))
		self._startDiscovery(jd)

	def _showDiscoveryResults(self, serverList: list):
		printl("serverList: " + str(serverList), self, "D")
		menu = []
		for server in serverList or []:
			printl("server: " + str(server), self, "D")
			menu.append((str(server.serverName) + " (" + str(server.server) + ":" + str(server.port) + ")", server,))
		if not menu:
			self.session.open(MessageBox, _("No servers discovered"), MessageBox.TYPE_INFO)
			return
		self.session.openWithCallback(self.useSelectedServerData, ChoiceBox, title=_("Select server"), list=menu)

	# ===========================================================================
	#
	# ===========================================================================
	def deleteConfirm(self, result):
		printl("", self, "S")

		if not result:
			return

		entry: EntryServer = self["entryList"].getCurrent()[4]
		sel = entry.settings
		settings: SettingsStorage = Singleton().getSettingsInstance()
		settings.serverConfigs.remove(sel)
		settings.writeToFile()
		self.updateList()

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPS_ServerConfig(ConfigListScreen, Screen, DPH_PlexScreen):

	useMappings = False
	useHomeUsers = False
	authenticated = False

	def __init__(self, session, entry: EntryServer, data: DiscoveredServer = None, cloneFrom: AbstractServerSettings = None):
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

		self._settings = Singleton().getSettingsInstance()

		if entry is None:
			self.newmode = 1
			if data is not None:
				sdata: ServerSettingsData = ServerSettings[data.type]
				self.current = sdata.factoryClass().createEmptyServerSettings(self._settings, data)
			elif cloneFrom is not None:
				sdata: ServerSettingsData = ServerSettings[cloneFrom.getType()]
				self.current = sdata.factoryClass().createServerSettings(self._settings)
				_copyServerFields(cloneFrom, self.current)
				try:
					self.current.id().setValue(self._settings.getUniqueId())
				except Exception:
					pass
				try:
					self.current.name().setValue(cloneFrom.name().getValue() + " " + _("(clone)"))
				except Exception:
					pass
			else:
				self.current = EmptyServerSettings(self._settings)
				self.current.onTypeChanged(self.serverTypeChanged)

			# Without this, the new server's Element is never attached to the
			# document and the object never lands in the live list: saving
			# would silently write nothing, and cancelling would crash below
			# in keyCancel(), which already expects to find it there.
			self._settings.registerNewServer(self.current)

		else:
			self.newmode = 0
			self.current = entry.settings
			printl("currentId: " + str(self.current.getIndex()), self, "D")

		self.cfglist = []
		ConfigListScreen.__init__(self, self.cfglist, session)

		self["config"].onSelectionChanged.append(self.updateHelp)

		self.onLayoutFinish.append(self.finishLayout)

		self.onShown.append(self.checkForPinUsage)

		# Safety net: registerNewServer() above already wired a brand-new/
		# cloned entry into the live server list before the user ever saw a
		# save/cancel choice. keyCancel() cleans it up on an explicit Cancel/
		# Exit, but any other way this screen closes (a stray key, a crash in
		# a callback) would otherwise leave it behind permanently. saveNow()
		# is the only place self._saved is set True.
		self._saved = False
		self.onClose.append(self._discardIfUnsaved)

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
			if self.current.pinRequired():
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
			if self.current.checkPin(enteredPin):
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
	def serverTypeChanged(self, configElement=None):
		self.createSetup()

	#===========================================================================
	#
	#===========================================================================
	def createSetup(self):
		printl("", self, "S")

		# EmptyServerSettings is only a placeholder shown while the user picks
		# a "Server Type" in the manual "Add server" flow. Once a real type is
		# chosen, swap it for an actual PlexSettings/JellyfinSettings instance
		# so the rest of the fields (and registerServer()) work as expected.
		if isinstance(self.current, EmptyServerSettings):
			selectedType = self.current.getSelectedType()
			if selectedType != EMPTY_SERVER_CONF:
				oldCurrent = self.current
				sdata: ServerSettingsData = ServerSettings[selectedType]
				self.current = sdata.factoryClass().createServerSettings(self._settings)
				self._settings.serverConfigs.remove(oldCurrent)
				self._settings.registerNewServer(self.current)

		self.cfglist = []

		hints: dict[str, Any] = self.current.setupServer(self.cfglist)
		self.useMappings = hints["useMappings"]
		self.useHomeUsers = hints["useHomeUsers"]

		self["config"].list = self.cfglist
		self["config"].l.setList(self.cfglist)

		self.setKeyNames()

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
		elif self.current.requireAuthentication():
			self["btn_yellowText"].setText(_("get local auth Token"))
			self["btn_yellowText"].show()
			self["btn_yellow"].show()
		else:
			self["btn_yellowText"].hide()
			self["btn_yellow"].hide()

		if (self.current.requireAuthentication()) and self.newmode == 0:
			if self.useHomeUsers:
				self["btn_redText"].setText(_("Home Users"))
				self["btn_redText"].show()
				self["btn_red"].show()
			else:
				self["btn_redText"].hide()
				self["btn_red"].hide()

			self["btn_blueText"].setText(_("(re)create remote Token"))

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

		if not self.current.isActive():
			# A disabled server needs neither a reachability check nor a
			# fresh token - nothing uses it until it is turned back on, and
			# skipping the network round-trip means simply flipping "State"
			# to No does not fail (or silently renew a token) on a server
			# that is unreachable right now for unrelated reasons.
			self.saveNow()
			printl("", self, "C")
			return

		if self.current.registerServer(self.session):
			if self.current.requireAuthentication():
				self.keyBlue()
			else:
				self.saveNow()
		elif isinstance(self.current, EmptyServerSettings):
			self.session.open(MessageBox, _("Please select a server type before saving."), MessageBox.TYPE_INFO)
		else:
			self.session.open(MessageBox, _("Could not reach the server.\nPlease check host, port and network connectivity."), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def saveNow(self, retval=None):
		printl("", self, "S")

		self._saved = True
		self._settings.writeToFile()

		self.close()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyCancel(self):
		printl("", self, "S")

		self._discardIfUnsaved()

		ConfigListScreen.cancelConfirm(self, True)

		printl("", self, "C")

	#===========================================================================
	# Removes a new/cloned server that was registered (registerNewServer(),
	# in __init__) but never actually saved - called both from keyCancel()
	# and unconditionally from onClose, so any way this screen closes without
	# saving leaves the server list exactly as it was before it was opened.
	#===========================================================================
	def _discardIfUnsaved(self):
		if self.newmode != 1 or self._saved:
			return
		settings: SettingsStorage = Singleton().getSettingsInstance()
		if self.current in settings.serverConfigs:
			settings.serverConfigs.remove(self.current)
			settings.writeToFile()

	#===========================================================================
	#
	#===========================================================================
	def keyYellow(self):
		printl("", self, "S")

		if self.useMappings:
			if self.current.supportServerMapping():
				self.session.open(DPS_Mappings, self.current)
			else:
				self.session.open(MessageBox, (_("Error:") + "\n%s \n" + _("unsupported mapping:")) % (_("Unsupported mapping for this server")), MessageBox.TYPE_INFO)

		elif self.current.requireAuthentication():
			success, info = self.current.buildAuthorization(self.session, mode=AuthorizationMode.LOCAL)

			if success:
				self.session.open(MessageBox, (_("Local Token:") + "\n%s \n" + _("for the user:") + "\n%s") % (info[AuthorizationResult.CREDENTIALS], info[AuthorizationResult.PRINCIPAL]), MessageBox.TYPE_INFO)
			else:
				self.session.open(MessageBox, (_("Error:") + "\n%s \n" + _("for the user:") + "\n%s") % (info[AuthorizationResult.ERROR], info[AuthorizationResult.PRINCIPAL]), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyBlue(self):
		printl("", self, "S")

		success, info = self.current.buildAuthorization(self.session, mode=AuthorizationMode.REMOTE)

		if success:
			# TYPE_INFO here used to save unconditionally on ANY dismissal -
			# OK or Cancel/Exit both just closed the box and fired the same
			# saveNow() callback, since it never looked at the retval. A user
			# who pressed Cancel/Exit expecting to abort the whole "add
			# server" flow got a silently saved, semi-configured server
			# anyway. TYPE_YESNO plus an explicit confirmed-only branch below
			# fixes that: only "Yes" saves, anything else leaves the entry
			# alone in the config screen (new/cloned entries still get
			# cleaned up on an explicit Cancel/Exit from there, same as
			# before - see _discardIfUnsaved()).
			self.session.openWithCallback(self._onRemoteAuthConfirmed, MessageBox, (_("Remote Token:") + "\n%s \n" + _("for the user:") + "\n%s \n" + _("with the id:") + "\n%s\n\n" + _("Save this server?")) %
										  (info[AuthorizationResult.CREDENTIALS], info[AuthorizationResult.PRINCIPAL], info[AuthorizationResult.ID]), MessageBox.TYPE_YESNO, default=True)
		else:
			# Do NOT save on a failed authentication: keySave() got here
			# automatically after the reachability check passed, but wrong/
			# missing credentials mean this entry is not actually usable yet.
			# Dismissing the error just returns to the config screen - the
			# entry (new or cloned) is only written to disk on a successful
			# auth, or discarded on an explicit Cancel/Exit (newmode == 1).
			self.session.open(MessageBox, (_("Error:") + "\n%s \n" + _("for the user:") + "\n%s") %
							  (info[AuthorizationResult.ERROR], info[AuthorizationResult.PRINCIPAL]), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _onRemoteAuthConfirmed(self, confirmed):
		printl("", self, "S")

		if confirmed:
			self.saveNow()
		# else: leave the config screen open with nothing saved - the user
		# can still change fields and retry, or Cancel/Exit as usual.

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def keyRed(self):
		printl("", self, "S")

		if self.useHomeUsers:
			self.session.open(DPS_Users, self.current)

		# self.session.open(MessageBox,(_("plex.tv Token:") + "\n%s \n" + _("plex.tv Localtoken:") + "\n%s \n"+ _("for the user:") + "\n%s") % (self.current.myplexToken.value, self.current.myplexLocalToken.value, self.current.myplexTokenUsername.value), MessageBox.TYPE_INFO)

		printl("", self, "C")

class EmptyServerSettings(AbstractServerSettings[None]):

	def __init__(self, owner: SettingsStorage):
		super().__init__(owner)
		serverTypeChoices = [(key, data.name) for key, data in ServerSettings.items()]
		self._serverType = ConfigSelection(choices=serverTypeChoices, default=EMPTY_SERVER_CONF)

		# Placeholder connection fields, only to satisfy AbstractServerSettings'
		# interface (ip()/port()/dns()/connectionType() are abstract there,
		# since their choices/defaults genuinely differ per real backend) -
		# this instance is swapped for a real PlexSettings/JellyfinSettings as
		# soon as a type is picked (see createSetup()), so these values are
		# never actually shown or used for a real connection.
		self._connectionType = BaseSettings[str, ConfigSelection]("connectionType", ConfigSelection(default="0", choices=[("0", _("IP")), ("1", _("DNS"))]), owner)
		self._ip = BaseSettings[str, ConfigIP]("ip", ConfigIP(default=[0, 0, 0, 0]), owner)
		self._dns = BaseSettings[str, ConfigText]("dns", ConfigText(default="", visible_width=50, fixed_size=False), owner)
		self._port = BaseSettings[int, ConfigInteger]("port", ConfigInteger(default=0, limits=(0, 65555)), owner)

	def connectionType(self) -> 'BaseSettings[str, ConfigSelection]':
		return self._connectionType

	def ip(self) -> 'BaseSettings[str, ConfigIP]':
		return self._ip

	def dns(self) -> 'BaseSettings[str, ConfigText]':
		return self._dns

	def port(self) -> 'BaseSettings[int, ConfigInteger]':
		return self._port

	def isReachable(self) -> bool:
		# Not a real server - "Add server" hasn't picked a type yet.
		return False

	def getSelectedType(self) -> str:
		return self._serverType.getValue()

	def onTypeChanged(self, callback) -> None:
		# keyLeft/keyRight already rebuild the config list after every value
		# change, but the "Server Type" field has multiple choices and is
		# normally changed via the OK-button ChoiceBox menu, which sets the
		# value directly without going through keyLeft/keyRight - so that
		# path never triggered a rebuild. Hooking the notifier covers both.
		self._serverType.addNotifier(callback, initial_call=False, immediate_feedback=True)

	def getIndex(self) -> int | None:
		return -1

	def requireAuthentication(self) -> bool:
		return False

	def registerServer(self, session) -> bool:
		return False

	def buildAuthorization(self, session, mode: AuthorizationMode) -> tuple[bool, dict[AuthorizationResult, str]]:
		return False, {}

	def supportServerMapping(self) -> bool:
		return False

	def listSupportedServerMappings(self, session) -> list[str] | None:
		return None

	def getName(self) -> str | None:
		return _("No Server")

	def getType(self) -> str:
		return EMPTY_SERVER_CONF

	def toEntryServer(self) -> EntryServer | None:
		return None

	def isActive(self) -> bool:
		return False

	def isAutostart(self) -> bool:
		return False

	def supportUsers(self) -> bool:
		return False

	def authenticateUser(self, session, principal: str, credential: str) -> tuple[bool, dict[AuthorizationResult, str]]:
		return (False, {AuthorizationResult.ERROR: _("No Server")})

	def pinRequired(self) -> bool:
		return False

	def checkPin(self, pin: str) -> bool:
		return True

	def setupServer(self, config: list[ConfigElement]) -> dict[str, Any]:
		config.append(getConfigListEntry(_(" > Server Type"), self._serverType, _("Select the type of server to add.")))
		res: dict[str, Any] = {
			"useMappings": False,
			"useHomeUsers": False
		}
		return res

	def getUserSwitchMode(self) -> str:
		return USER_SWITCH_NONE

	def getCurrentUserDisplayName(self) -> str | None:
		return None

	def getCurrentUserAccessToken(self) -> str | None:
		return None

	def getCloneExcludeFields(self) -> set[str]:
		return set()

	def _writeValue(self, value: T) -> None:
		pass

	def _readValue(self) -> T:
		pass

