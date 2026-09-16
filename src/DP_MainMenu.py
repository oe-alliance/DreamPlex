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
from dataclasses import dataclass

from enigma import eTimer

from Components.ActionMap import HelpableActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label

from Screens.MessageBox import MessageBox
from . import SettingsStorage, AbstractServerSettings, ServerSettingsData, ServerSettings
from .DP_MediaLibrary import DP_MediaLibrary

from .DP_SystemCheck import DPS_SystemCheck
from .DP_Settings import DPS_Settings
from .DP_Server import DPS_Server
from .DP_About import DPS_About
from .DP_ServerMenu import DPS_ServerMenu, DPS_List
from .DP_Syncer import DPS_Syncer

from .DPH_Singleton import Singleton
from .DPH_MovingLabel import DPH_HorizontalMenu
from .DPH_WOL import wake_on_lan
from .DPH_ScreenHelper import DPH_ScreenHelper, DPH_Screen

from .__common__ import printl2 as printl, saveLiveTv
from .__plugin__ import Plugin
from . import _  # _ is translation

#===============================================================================
#
#===============================================================================

@dataclass
class SelectionItem:
	title: str
	type: str | int
	data: str | AbstractServerSettings | dict[str, str]


class DPS_MainMenu(DPH_Screen, DPH_HorizontalMenu, DPH_ScreenHelper):

	g_horizontal_menu = False

	selectedEntry = None
	g_serverConfig = None

	nextExitIsQuit = True
	currentService = None
	plexInstance: DP_MediaLibrary = None
	selectionOverride = None

	#===========================================================================
	#
	#===========================================================================
	def __init__(self, session, allowOverride=True):
		printl("", self, "S")
		DPH_Screen.__init__(self, session)
		DPH_ScreenHelper.__init__(self)

		self.allowOverride = allowOverride

		# post Wake on Lan wait, see sleepNow()
		self._wolTimer = None

		self.selectionOverride: SelectionItem | None = None
		printl("selectionOverride:" + str(self.selectionOverride), self, "D")
		self.session = session

		# save liveTvData
		saveLiveTv(self.session.nav.getCurrentlyPlayingServiceReference())

		self.initScreen("main_menu")
		self.initMenu()

		if self.g_horizontal_menu:
			self.setHorMenuElements(depth=2)
			self.translateNames()

		self["title"] = StaticText()

		self["menu"] = DPS_List()

		# Carousel skin only: the space under the miniTV that DPS_ServerMenu's
		# hero banner would occupy is empty here, since there is no server/
		# media library yet to suggest anything from (see DP_ServerMenu.py's
		# own comment on why the hero lives there, not here). Filled instead
		# with a static marquee image (skin.xml ePixmap, no Python) plus two
		# translatable tagline lines over it - the wordmark baked into the
		# image is the brand name, not translated.
		self._fillerEnabled = Singleton().getSettingsInstance().skinName.getValue() == "Carousel"
		if self._fillerEnabled:
			self["menuFillerLine1"] = Label()
			self["menuFillerLine2"] = Label()
			# Contextual hint next to the marquee, updated on every selection
			# change (see _updateMenuHint()) - "what happens if I press OK on
			# this row", since the row itself only shows a name/number.
			self["menuHintEyebrow"] = Label()
			self["menuHintTitle"] = Label()
			self["menuHintBody"] = Label()
			self["menu"].onSelectionChanged.append(self._updateMenuHint)

		self["actions"] = HelpableActionMap(self, "DP_MainMenuActions",
											{
												"ok": (self.okbuttonClick, ""),
												"left": (self.left, ""),
												"right": (self.right, ""),
												"up": (self.up, ""),
												"down": (self.down, ""),
												"cancel": (self.cancel, ""),
												# Direct-jump shortcuts for the Carousel skin's vertical
												# sidebar (item N gets digit N) - harmless elsewhere: a
												# skin that never shows the digit just leaves this
												# unused, same idiom as the Help-key descriptions below.
												"shortcut1": (lambda: self._onShortcut(1), _("Jump to menu item 1")),
												"shortcut2": (lambda: self._onShortcut(2), _("Jump to menu item 2")),
												"shortcut3": (lambda: self._onShortcut(3), _("Jump to menu item 3")),
												"shortcut4": (lambda: self._onShortcut(4), _("Jump to menu item 4")),
												"shortcut5": (lambda: self._onShortcut(5), _("Jump to menu item 5")),
												"shortcut6": (lambda: self._onShortcut(6), _("Jump to menu item 6")),
												"shortcut7": (lambda: self._onShortcut(7), _("Jump to menu item 7")),
												"shortcut8": (lambda: self._onShortcut(8), _("Jump to menu item 8")),
												"shortcut9": (lambda: self._onShortcut(9), _("Jump to menu item 9")),
											}, -2)

		if Singleton().getSettingsInstance().stopLiveTvOnStartup.getValue():
			self.session.nav.stopService()

		self.onFirstExecBegin.append(self.onExec)
		self.onLayoutFinish.append(self.finishLayout)
		self.onShown.append(self.checkSelectionOverride)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def finishLayout(self):
		printl("", self, "S")

		self.setTitle(_("Main Menu"))

		if self._fillerEnabled:
			self["menuFillerLine1"].setText(_("Your cinema, at home"))
			self["menuFillerLine2"].setText(_("The show is about to start"))

		if self.miniTv:
			self.initMiniTv()

		# get all our servers as list
		self.getServerList(self.allowOverride)

		# now that our mainMenuList is populated we set the list element
		self["menu"].setList(self.mainMenuList)

		# save the mainMenuList for later usage
		self.menu_main_list = self["menu"].list

		self.refreshMenu()

		if self._fillerEnabled:
			# onSelectionChanged (registered above) fires on later moves, but
			# setList() just above does not retroactively fire it for the
			# row it lands on first - without this the hint stays blank
			# until the user actually presses up/down once.
			self._updateMenuHint()

		printl("", self, "C")

	#===============================================================================
	# One short line each, per row "kind" - the same tags DPS_MainMenu's own
	# picon widgets already key off of (MenuEntryCompare in skin.xml:
	# serverEntry/settingsEntry/aboutEntry/systemEntry/LiveTv), so this
	# reuses a distinction the skin already makes rather than inventing a
	# new one. Falls back to a generic "Open <name>" for anything else
	# (e.g. "settingsEntry" rows from getSettingsMenu()'s own submenu -
	# Settings/Server/Systemcheck/Backdrops - there is no single kind tag
	# reused across those four, so a bespoke line per row is not worth it).
	#===============================================================
	def _updateMenuHint(self):
		printl("", self, "S")

		current = self["menu"].getCurrent()
		if current is None:
			printl("", self, "C")
			return

		name = current[0]
		kind = current[2] if len(current) > 2 else None

		if kind == "serverEntry":
			eyebrow = _("Server")
			title = _("Enter %s") % name
			body = _("Browse Movies, TV Shows and Music on this server.")
		elif kind == "systemEntry":
			eyebrow = _("Settings")
			title = _("Open Settings")
			body = _("Configure the plugin: servers, skin, cache and more.")
		elif kind == "LiveTv":
			eyebrow = _("Live TV")
			title = _("Back to live TV")
			body = ""
		elif kind == "aboutEntry":
			eyebrow = _("Info")
			title = _("About")
			body = _("Information and credits for the plugin.")
		else:
			eyebrow = ""
			title = _("Open %s") % name
			body = ""

		self["menuHintEyebrow"].setText(eyebrow)
		self["menuHintTitle"].setText(title)
		self["menuHintBody"].setText(body)

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def okbuttonClick(self):
		printl("", self, "S")

		# this is used to step in directly into a server when there is only one entry in the serverlist
		if self.selectionOverride is not None:
			selection = self.selectionOverride

			# because we change the screen we have to unset the information to be able to return to main menu
			self.selectionOverride = None
		else:
			selection = self["menu"].getCurrent()

		printl("selection = " + str(selection), self, "D")

		if selection is not None:

			self.selectedEntry = selection[1]
			printl("selected entry " + str(self.selectedEntry), self, "D")

			if type(self.selectedEntry) is int:
				printl("selected entry is int", self, "D")

				if self.selectedEntry == Plugin.MENU_MAIN:
					printl("found Plugin.MENU_MAIN", self, "D")
					self["menu"].setList(self.menu_main_list)
					try:
						self["menu"].top()
					except Exception:
						try:
							self["menu"].setIndex(0)
						except Exception:
							pass

				elif self.selectedEntry == Plugin.MENU_SERVER:
					printl("found Plugin.MENU_SERVER", self, "D")

					self.g_serverConfig: AbstractServerSettings = selection[3]
					# checkServerState() checks connectivity and, if reachable,
					# opens DPS_ServerMenu for this server - without this call
					# nothing happened at all after selecting a server here.
					self.checkServerState()

				elif self.selectedEntry == Plugin.MENU_SYSTEM:
					printl("found Plugin.MENU_SYSTEM", self, "D")
					self["menu"].setList(self.getSettingsMenu())
					try:
						self["menu"].top()
					except Exception:
						try:
							self["menu"].setIndex(0)
						except Exception:
							pass
					self.setTitle(_("System"))
					self.refreshMenu()

					if self.g_horizontal_menu:
						self.refreshOrientationHorMenu(0)

			elif type(self.selectedEntry) is str:
				printl("selected entry is string", self, "D")

				if selection[1] == "DPS_Settings":
					self.session.open(DPS_Settings)

				elif selection[1] == "DPS_Server":
					self.session.open(DPS_Server)

				elif selection[1] == "DPS_SystemCheck":
					self.session.open(DPS_SystemCheck)

				elif selection[1] == "DPS_About":
					self.session.open(DPS_About)

				elif selection[1] == "LiveTv":
					self.exit()

				elif selection[1] == "DPS_Syncer":
					self.session.open(DPS_Syncer, "render")

			else:
				pass

			printl("", self, "C")

	#===========================================================================
	# Direct-jump shortcut (see keymap.xml/"shortcutN" above) - digit N moves
	# the selection to the Nth row of whatever list is currently shown
	# (mainMenuList or, after entering System, getSettingsMenu()'s list) and
	# selects it immediately, mirroring okbuttonClick(). The ordinal label
	# itself (shown by the Carousel skin's sidebar template) is appended as
	# the last tuple element by _appendShortcutLabels() below - this only
	# ever reads self["menu"]'s current row count/index, so it stays correct
	# for whichever list is loaded.
	#===========================================================================
	def _onShortcut(self, digit):
		printl("digit: " + str(digit), self, "S")

		index = digit - 1
		try:
			if 0 <= index < len(self["menu"].list):
				self["menu"].setIndex(index)
				self.okbuttonClick()
		except Exception as ex:
			printl("Exception(" + str(type(ex)) + "): " + str(ex), self, "W")

		printl("", self, "C")

	#===========================================================================
	# Appends a 1-9 ordinal label to each row tuple, for the Carousel skin's
	# sidebar template to display next to each item - rows beyond the 9th
	# get an empty label (no single-digit shortcut is possible for them
	# anyway, see _onShortcut()). Kept as a separate pass over an
	# already-built list rather than threading it through every individual
	# .append() call site, since those already build tuples of different
	# lengths (server rows carry the AbstractServerSettings as a 4th
	# element, the rest don't) - appending here, once, keeps every row's
	# *existing* indices (MenuEntryCompare's, okbuttonClick()'s
	# selection[1]/[3], ...) untouched.
	#
	# Padding every row to the same length (padTo) BEFORE appending the
	# label is what keeps the label itself at one fixed index across every
	# row too - a skin template reads a single fixed index for every row it
	# renders, so a label that landed at index 3 on a 3-element row and
	# index 4 on a 4-element row (the naive "just append" version of this)
	# would be unreadable by any template.
	#===========================================================================
	def _appendShortcutLabels(self, menuList, padTo=4):
		result = []
		for i, row in enumerate(menuList):
			row = tuple(row)
			if len(row) < padTo:
				row = row + (None,) * (padTo - len(row))
			result.append(row + (str(i + 1) if i < 9 else "",))
		return result

	#===========================================================================
	#
	#===========================================================================
	def getSettingsMenuList(self):
		printl("", self, "S")

		self["menu"].setList(self.getSettingsMenu())
		self.refreshMenu()

		printl("", self, "C")

	#==========================================================================
	#
	#==========================================================================
	def up(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			self.left()
		else:
			self["menu"].selectPrevious()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def down(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			self.right()
		else:
			self["menu"].selectNext()

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def right(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			try:
				self.refreshOrientationHorMenu(+1)
			except Exception as ex:
				printl("Exception(" + str(type(ex)) + "): " + str(ex), self, "W")
				self["menu"].selectNext()
		else:
			# RIGHT mirrors OK (enter the highlighted row) instead of paging -
			# pageDown() was a no-op on this screen's simple vertical list
			# anyway, and matches the same fix already applied to
			# DP_ServerMenu.py's sidebar (see its right()/left() for the full
			# reasoning) - Right/Left now behave the same way on both of the
			# Carousel skin's vertical-sidebar screens.
			self.okbuttonClick()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def left(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			try:
				self.refreshOrientationHorMenu(-1)
			except Exception as ex:
				printl("Exception(" + str(type(ex)) + "): " + str(ex), self, "W")
				self["menu"].selectPrevious()
		else:
			# LEFT falls straight through to going back, same reasoning as
			# DP_ServerMenu.py's left() - pageUp() was always a no-op here.
			self.cancel()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def exit(self):
		printl("", self, "S")

		# we call here explict to avoid memory blocking if there are still something
		self.closePlugin()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def cancel(self):
		printl("", self, "S")

		if self.nextExitIsQuit:
			self.exit()

		else:
			self.setTitle(_("Main Menu"))

			printl("selectedEntry " + str(self.selectedEntry), self, "D")
			self.getServerList()

			self["menu"].setList(self.menu_main_list)
			self.nextExitIsQuit = True

			if self.g_horizontal_menu:
				self.refreshOrientationHorMenu(0)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def refreshMenu(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			self.refreshOrientationHorMenu(0)

		printl("", self, "C")

	#===============================================================================
	# HELPER
	#===============================================================================

	#===============================================================================
	#
	#===============================================================================
	def Error(self, error):
		printl("", self, "S")

		self.session.open(MessageBox, _("UNEXPECTED ERROR:") + "\n%s" % error, MessageBox.TYPE_INFO)

		printl("", self, "C")

	#=======================================================================
	#
	#=======================================================================
	def getSettingsMenu(self):
		printl("", self, "S")

		mainMenuList = []

		mainMenuList.append((_("Settings"), "DPS_Settings", "settingsEntry"))
		mainMenuList.append((_("Server"), "DPS_Server", "settingsEntry"))
		mainMenuList.append((_("Systemcheck"), "DPS_SystemCheck", "settingsEntry"))
		mainMenuList.append((_("Backdrops"), "DPS_Syncer", "settingsEntry"))

		mainMenuList = self._appendShortcutLabels(mainMenuList)

		self.nextExitIsQuit = False

		printl("", self, "C")
		return mainMenuList

	#===============================================================================
	#
	#===============================================================================
	def checkSelectionOverride(self):
		printl("", self, "S")
		printl("self.selectionOverride: " + str(self.selectionOverride), self, "D")

		if self.selectionOverride is not None:
			self.okbuttonClick()

		printl("", self, "C")
	#===============================================================================
	#
	#===============================================================================

	def getServerList(self, allowOverride=True):
		printl("", self, "S")

		self.mainMenuList = []

		# add servers to list
		settings: SettingsStorage = Singleton().getSettingsInstance()
		for serverConfig in settings.serverConfigs:

			# only add the server if state is active
			if serverConfig.isActive():
				serverName = serverConfig.getName()

				self.mainMenuList.append((serverName, Plugin.MENU_SERVER, "serverEntry", serverConfig))

				# automatically enter the server if wanted
				if serverConfig.isAutostart() and allowOverride:
					printl("here", self, "D")
					self.selectionOverride = [serverName, Plugin.MENU_SERVER, "serverEntry", serverConfig]

		self.mainMenuList.append((_("System"), Plugin.MENU_SYSTEM, "systemEntry"))
		self.mainMenuList.append((_("LiveTv"), "LiveTv", "LiveTv"))
		self.mainMenuList.append((_("About"), "DPS_About", "aboutEntry"))

		self.mainMenuList = self._appendShortcutLabels(self.mainMenuList)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def checkServerState(self):
		printl("", self, "S")

		self.g_wolon = self.g_serverConfig.wakeOnLanAvailable()
		self.g_wakeserver = str(self.g_serverConfig.wol_mac().getValue())
		self.g_woldelay = int(self.g_serverConfig.wol_delay().getValue())
		isOnline = self.g_serverConfig.isReachable()

		if isOnline:
			stateText = "Online"
		else:
			stateText = "Offline"

		printl("Server State: " + str(stateText), self, "I")
		if not isOnline:
			if self.g_wolon:
				self.showWakeMessage()

			else:
				self.showOfflineMessage()
		else:
			self.session.open(DPS_ServerMenu, self.g_serverConfig)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def startServerMenu(self, answer):
		printl("", self, "S")
		printl("answer: " + str(answer), self, "D")

		if answer:
			self.checkServerState()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showWakeMessage(self):
		printl("", self, "S")

		self.session.openWithCallback(self.executeWakeOnLan, MessageBox, _("Server seems to be offline. Start with Wake on Lan settings? \n\nPlease note: \nIf you press yes the spinner will run for " + str(self.g_woldelay) + " seconds. \nAccording to your settings."), MessageBox.TYPE_YESNO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showOfflineMessage(self):
		printl("", self, "S")

		self.session.openWithCallback(self.startServerMenu, MessageBox, _("Server seems to be offline. Please check your your settings or connection!\n Retry?"), MessageBox.TYPE_YESNO)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def executeWakeOnLan(self, confirm):
		printl("", self, "S")

		if confirm:
			# User said 'yes'
			printl("Wake On LAN: " + str(self.g_wolon), self, "D")

			for i in range(1, 12):
				if not self.g_wakeserver == "":
					try:
						printl("Waking server " + str(i) + " with MAC: " + self.g_wakeserver, self, "D")
						ipValue = self.g_serverConfig.ip().getValue()
						broadcastIp = "%d.%d.%d.255" % (ipValue[0], ipValue[1], ipValue[2])
						printl("broadcast ip: " + broadcastIp, self, "D")
						wake_on_lan(self.g_wakeserver, broadcastIp)
					except ValueError:
						printl("Incorrect MAC address format for server " + str(i), self, "D")
					except Exception as e:
						printl("WOL Error: " + str(e), self, "D")
			self.sleepNow()
		else:
			# User said 'no'
			self.refreshMenu()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def sleepNow(self):
		printl("", self, "S")

		# Wait for the server to finish booting after the Wake on Lan.
		# With time.sleep() the enigma2 main loop would stall for the whole
		# configured delay (tens of seconds), leaving the box unresponsive to
		# the remote control; a one-shot eTimer keeps the interface alive.
		self._wolTimer = eTimer()
		self._wolTimer.callback.append(self._onWolDelayElapsed)
		self._wolTimer.start(int(self.g_woldelay) * 1000, True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _onWolDelayElapsed(self):
		printl("", self, "S")

		if self._wolTimer is not None:
			self._wolTimer.stop()
			self._wolTimer = None
		self.checkServerState()

		printl("", self, "C")

	#===============================================================================
	# ADDITIONAL STARTUPS
	#===============================================================================

	#===========================================================================
	#
	#===========================================================================
	def onExec(self):
		printl("", self, "S")

		printl("", self, "C")
