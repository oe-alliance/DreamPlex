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
from typing import TYPE_CHECKING

from enigma import eTimer, ePicLoad

from Tools.Directories import fileExists

from Components.ActionMap import HelpableActionMap
from Components.AVSwitch import AVSwitch
from Components.Input import Input
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.Pixmap import Pixmap
from Components.Label import Label
from Components.ProgressBar import ProgressBar

from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.InputBox import InputBox
from .DP_Player import DP_Player
from .DP_LibShows import DP_LibShows
from . import SettingsStorage, AbstractServerSettings, ServerSettings, ServerSettingsData
from .DP_SettingsStorage import AuthorizationResult, USER_SWITCH_LOCAL_PROFILES

from .DPH_Singleton import Singleton
from . import DPH_Vault
from .DPH_MovingLabel import DPH_HorizontalMenu
from .DP_HelperScreens import DPS_InputBox, DPS_TextInputBox
from .DP_Syncer import DPS_Syncer
from .DPH_ScreenHelper import DPH_ScreenHelper, DPH_Screen, DPH_Filter, DPH_PlexScreen
from .DP_ViewFactory import getGuiElements
from .DP_Users import DPS_Users

from .__common__ import printl2 as printl, getLiveTv
from .__plugin__ import Plugin
from . import _  # _ is translation

# DP_MainMenu imports DPS_ServerMenu from this module at module level, so
# importing SelectionItem back from DP_MainMenu here would be circular: by
# the time DP_MainMenu reaches that import, this module is still executing
# and DP_MainMenu.SelectionItem (defined further down in that file) does not
# exist yet. SelectionItem is only used below as a type annotation, so it is
# deferred to TYPE_CHECKING instead.
if TYPE_CHECKING:
	from .DP_MainMenu import SelectionItem

#===============================================================================
#
#===============================================================================

# Subclass of List to support horizontal menu


class DPS_List(List):
	def __init__(self):
		List.__init__(self)

	def selectPrevious(self):
		if self.getIndex() - 1 < 0:
			self.index = self.count() - 1
		else:
			self.index -= 1
		self.setIndex(self.index)

	def selectNext(self):
		if self.getIndex() + 1 >= self.count():
			self.index = 0
		else:
			self.index += 1
		self.setIndex(self.index)


class DPS_ServerMenu(DPH_Screen, DPH_HorizontalMenu, DPH_ScreenHelper, DPH_Filter, DPH_PlexScreen):

	g_horizontal_menu = False

	selectedEntry = None
	g_serverConfig = None

	g_serverDataMenu = None
	currentService = None
	mediaLibraryInstance = None
	selectionOverride = None
	secondRun = False
	menuStep = 0  # vaule how many steps we made to restore navigation data
	currentMenuDataDict = {}
	currentIndexDict = {}
	isHomeUser = False

	#===========================================================================
	#
	#===========================================================================
	def __init__(self, session, g_serverConfig: AbstractServerSettings):
		printl("", self, "S")
		DPH_Screen.__init__(self, session)
		DPH_ScreenHelper.__init__(self)
		DPH_Filter.__init__(self)
		DPH_PlexScreen.__init__(self)

		self.selectionOverride: SelectionItem | None = None
		printl("selectionOverride:" + str(self.selectionOverride), self, "D")
		self.session = session

		self.g_serverConfig = g_serverConfig
		s: ServerSettingsData = ServerSettings[self.g_serverConfig.getType()]
		self.mediaLibraryInstance = s.factoryClass().createMediaLibrary(session, self.g_serverConfig)
		# DP_View/DP_Player/DP_LibMain read the current library through the
		# global Singleton (Singleton().getMediaLibrary()), not through a
		# reference passed down from here. It used to only get set as a side
		# effect of the Plex auth/registration flow, so opening an existing
		# Jellyfin server (which has no such flow on a plain open) left it at
		# None and crashed with AttributeError: 'NoneType' object has no
		# attribute 'getServerName' the moment a media view screen opened.
		Singleton().getMediaLibrary(self.mediaLibraryInstance)
		self.settings: SettingsStorage = Singleton().getSettingsInstance()
		self.guiElements = getGuiElements()

		self.initScreen("server_menu")
		self.initMenu()

		if self.g_horizontal_menu:
			self.setHorMenuElements(depth=2)
			self.translateNames()

		self["title"] = StaticText()

		self["menu"] = DPS_List()

		# Priority -3, not -2: DPH_Filter (one of this screen's own base
		# classes, __init__'d just above) already binds KEY_1-9 to its own
		# "DP_FilterMenuActions" context at -2, for its type-ahead T9 search
		# feature - a DIFFERENT context name does NOT avoid the collision
		# (see [[project-dreamplex-actionmap-priority]]: one physical
		# keypress resolves to a single winner across every bound context,
		# by priority, not per-context). Equal priority ties go to
		# whichever ActionMap was constructed first, which was
		# DPH_Filter's - so every digit press was silently going to
		# onNumberKey() (multi-tap letter search) instead of the shortcuts
		# below. -3 beats it outright.
		self["actions"] = HelpableActionMap(self, "DP_MainMenuActions",
											{
												"ok": (self.okbuttonClick, ""),
												"left": (self.left, ""),
												"right": (self.right, ""),
												"up": (self.up, ""),
												"down": (self.down, ""),
												"cancel": (self.cancel, ""),
												# RED had no help text and no on-screen button anywhere
												# (not even in the default skin) - pressing it silently
												# opened a full server sync/cache-download with zero
												# warning. Both fixed: real help text here, plus a
												# visible btn_red/btn_redText (see __init__/finishLayout,
												# same pattern as btn_green just below).
												# Renamed from "Sync/cache server data" - it only ever
												# downloads posters/backdrops and metadata into the local
												# cache (see DP_Syncer.syncThroughMediaLibrary()), never
												# the actual video files. "Sync" read as "mirror the whole
												# server locally", which is not what happens.
												"red": (self.onKeyRed, _("Download posters and info (not videos)")),
												"green": (self.onKeyGreen, _("Switch user")),
												# Only meaningful when the hero banner is enabled -
												# onKeyBlue() no-ops otherwise. Bound unconditionally
												# since it is cheap and this ActionMap is built before
												# self._heroEnabled is known (see below).
												"blue": (self.onKeyBlue, _("Play the hero suggestion")),
												# Same direct-jump shortcuts as DPS_MainMenu (see
												# DP_MainMenu.py) - this screen shares its
												# "DP_MainMenuActions" keymap.xml context.
												"shortcut1": (lambda: self._onShortcut(1), _("Jump to menu item 1")),
												"shortcut2": (lambda: self._onShortcut(2), _("Jump to menu item 2")),
												"shortcut3": (lambda: self._onShortcut(3), _("Jump to menu item 3")),
												"shortcut4": (lambda: self._onShortcut(4), _("Jump to menu item 4")),
												"shortcut5": (lambda: self._onShortcut(5), _("Jump to menu item 5")),
												"shortcut6": (lambda: self._onShortcut(6), _("Jump to menu item 6")),
												"shortcut7": (lambda: self._onShortcut(7), _("Jump to menu item 7")),
												"shortcut8": (lambda: self._onShortcut(8), _("Jump to menu item 8")),
												"shortcut9": (lambda: self._onShortcut(9), _("Jump to menu item 9")),
											}, -3)

		self["btn_red"] = Pixmap()
		self["btn_redText"] = Label()

		self["btn_green"] = Pixmap()
		self["btn_green"].hide()
		self["btn_greenText"] = Label()

		self["text_HomeUserLabel"] = Label()
		self["text_HomeUser"] = Label()

		# --- Carousel skin's rotating "hero" banner (see
		# DP_MediaLibrary.getHeroSuggestions()) - only on skins that
		# actually declare skinName == "Carousel". Checking the settings
		# value directly (not "'heroPoster' in self", which would be True
		# regardless of the skin - a self[name] = Widget() assignment
		# succeeds even when skin.xml has no matching element) is what
		# keeps the fetch/timer from ever running on default/BlueMod. This
		# screen (not DPS_MainMenu) is where the hero lives: it is the
		# first screen with an actual mediaLibraryInstance/active server to
		# ask for suggestions - DPS_MainMenu (the server picker) has none yet.
		self._heroEnabled = Singleton().getSettingsInstance().skinName.getValue() == "Carousel"
		if self._heroEnabled:
			self["heroPoster"] = Pixmap()
			self["heroTitle"] = Label()
			self["heroMeta"] = Label()
			self["heroSummary"] = Label()
			# "Continue watching" vs "Suggested" - see getHeroSuggestions()'s
			# heroKind tag and _updateHeroDisplay().
			self["heroKindBadge"] = Label()
			# Sits behind heroPoster, slightly larger, same amber used for the
			# sidebar's own selected-row highlight (skinParams "highlighted")
			# - shown only while the hero actually has focus, so OK/BLUE
			# playing it is never a surprise. Before this, the only cue was a
			# "▶ " prefix in heroTitle's text, easy to miss (live-tested: it
			# was missed).
			self["heroFocusFrame"] = Label()
			self["heroFocusFrame"].hide()
			self._heroPicLoad = ePicLoad()
			self._heroScale = AVSwitch().getFramebufferScale()
			self._heroCandidates = []
			self._heroIndex = 0
			self._heroLoopCount = 0
			self._heroFocused = False
			self._heroTimer = eTimer()
			self._heroTimer.callback.append(self._onHeroTimerTick)
			self.onClose.append(self._stopHeroTimer)

			# Blue-key shortcut to play the current hero suggestion directly,
			# without having to navigate focus onto it first (added after
			# live feedback that Left/Right no longer reach the hero once
			# they were repurposed as page/enter - see right()/down()/up()
			# below). btn_blue/btn_blueText follow the same self[name] =
			# Widget() pattern as the rest of this screen's color buttons -
			# harmless if the active skin doesn't declare them.
			self["btn_blue"] = Pixmap()
			self["btn_blue"].hide()
			self["btn_blueText"] = Label()
			self["btn_blueText"].hide()

			# Small countdown bar showing time left until the hero rotates
			# to the next suggestion - re-armed every real rotation-timer
			# tick (see _armHeroCountdown()), ticks down independently on
			# its own short-interval timer for a smooth animation.
			self["heroProgress"] = ProgressBar()
			self["heroProgress"].hide()
			self._heroIntervalTotalMs = 0
			self._heroElapsedMs = 0
			self._heroProgressTimer = eTimer()
			self._heroProgressTimer.callback.append(self._onHeroProgressTick)

		self.onLayoutFinish.append(self.finishLayout)
		self.onLayoutFinish.append(self.getInitialData)
		self.onLayoutFinish.append(self.checkSelectionOverride)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def finishLayout(self):
		printl("", self, "S")

		self.setTitle(_("Server Menu"))

		# first we set the pics for buttons
		self.setColorFunctionIcons()

		# always available (unlike btn_green, gated on supportUsers() below) -
		# see onKeyRed()/the "red" action above for why this needed a visible
		# label at all.
		self["btn_redText"].setText(_("Catalog"))

		if self.miniTv:
			self.initMiniTv()

		if self.g_serverConfig.supportUsers():
			self["btn_green"].show()
			self["btn_greenText"].setText(_("Switch User"))
			self["text_HomeUserLabel"].setText(_("Current User:"))

			# Both fields come from AbstractServerSettings.
			# getCurrentUserDisplayName()/getCurrentUserAccessToken() -
			# each backend resolves them from its own notion of "current
			# user" (Plex: active home user or the plex.tv account;
			# Jellyfin: the locally switched-to user).
			try:
				self["text_HomeUser"].setText(self.g_serverConfig.getCurrentUserDisplayName() or "")
				token = self.g_serverConfig.getCurrentUserAccessToken()
				if token:
					self.mediaLibraryInstance.setAccessTokenHeader(self.mediaLibraryInstance.g_currentServer, token)
			except Exception:
				pass

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def getInitialData(self):
		printl("", self, "S")

		self.getServerData()

		# save the mainMenuList for later usage
		self.menu_main_list: list[SelectionItem] = self["menu"].list

		if self.g_horizontal_menu:
			# init horizontal menu
			self.refreshOrientationHorMenu(0)

		if self._heroEnabled:
			self._fetchHeroCandidates()

		printl("", self, "C")

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
	# KEYSTROKES
	#===============================================================================

	#===============================================================
	#
	#===============================================================
	def onKeyRed(self):
		printl("", self, "S")

		self.session.open(DPS_Syncer, "sync", self.g_serverConfig,)

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def onKeyGreen(self):
		printl("", self, "S")

		# Which "switch user" UI flow to open is declared by the backend
		# itself (AbstractServerSettings.getUserSwitchMode()), not decided
		# here from a hardcoded server-type string - see USER_SWITCH_* in
		# DP_SettingsStorage.py.
		mode = None
		try:
			mode = self.g_serverConfig.getUserSwitchMode()
		except Exception:
			mode = None

		if mode == USER_SWITCH_LOCAL_PROFILES:
			# Show the list of saved users, with an option to add a new one
			self.displayJellyfinUsersMenu()
		else:
			self.displayOptionsMenu()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def displayOptionsMenu(self):
		printl("", self, "S")

		functionList = []

		# add plex.tv User as first one
		functionList.append((self.g_serverConfig.myplexTokenUsername().getValue(), self.g_serverConfig.myplexPin().getValue(), self.g_serverConfig.myplexToken().getValue(), False, self.g_serverConfig.myplexId().getValue()))

		# now add all home users
		self.homeUsersObject = DPS_Users(self.session, self.g_serverConfig.id().getValue(), self.mediaLibraryInstance)
		homeUsersFromServer = self.homeUsersObject["content"].getHomeUsersFromServer()

		if homeUsersFromServer is not None:
			for user in homeUsersFromServer.findall('user'):
				self.lastUserId = user.attrib.get("id")
				self.currentHomeUsername = user.attrib.get("username")
				self.currentPin = user.attrib.get("pin")
				self.currentHomeUserToken = user.attrib.get("token")

				functionList.append((self.currentHomeUsername, self.currentPin, self.currentHomeUserToken, True, self.lastUserId))

		self.session.openWithCallback(self.displayOptionsMenuCallback, ChoiceBox, title=_("Home Users"), list=functionList)

		printl("", self, "C")

	#===============================================================
	# Jellyfin user login flow (username/password)
	#===============================================================
	def displayJellyfinUsersMenu(self):
		try:
			lst = []
			# Option: add user
			lst.append((_("Add user"), "__add__"))

			# Utenti salvati
			users = self.g_serverConfig.listUsers() if hasattr(self.g_serverConfig, 'listUsers') else []
			for u in users or []:
				title = u.username.getValue()
				uid = u.id.getValue()
				label = title
				if self._hasPin(u):
					label = title + " " + _("(PIN protected)")
				lst.append((label, uid))

			self.session.openWithCallback(self._onJellyfinUsersMenuSelected, ChoiceBox, title=_("Users"), list=lst)
		except Exception as e:
			self.session.open(MessageBox, str(e), MessageBox.TYPE_ERROR)

	def _jellyfinUserByUid(self, uid):
		try:
			for u in self.g_serverConfig.listUsers():
				if u.id.getValue() == uid:
					return u
		except Exception:
			pass
		return None

	def _hasPin(self, user) -> bool:
		# The token being an DPH_Vault blob IS the "this profile has a pin"
		# signal - there is no separate plaintext pin stored anywhere to
		# read back and compare against, on purpose: storing the pin
		# alongside the very data it is meant to gate would have made it
		# pointless (readable straight out of settings.xml, no need to guess
		# it). "Correct" is proven by DPH_Vault.decrypt() actually succeeding
		# on the token with whatever the user typed, nothing else.
		#
		# The one exception is a profile protected by the earlier build,
		# which stored the pin in the now-unused <pin> field next to a still-
		# plaintext token - that legacy shape is recognised here so its
		# "protected" badge keeps showing, and gets migrated to real
		# encryption the moment it is next unlocked (see
		# _onJellyfinSwitchPinEntered).
		if DPH_Vault.isEncrypted(user.token.getValue()):
			return True
		return DPH_Vault.hasPin(user.pin.getValue())

	def _onJellyfinUsersMenuSelected(self, choice):
		if not choice:
			return
		label, uid = choice
		if uid == "__add__":
			self.askJellyfinUsername()
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return

		hasPin = self._hasPin(user)
		lst = [(_("Switch to this user"), "switch")]
		if hasPin:
			lst.append((_("Change PIN"), "change_pin"))
			lst.append((_("Remove PIN"), "remove_pin"))
		else:
			lst.append((_("Set PIN"), "set_pin"))

		self._pendingJellyfinUserUid = uid
		self.session.openWithCallback(self._onJellyfinUserActionSelected, ChoiceBox, title=label, list=lst)

	def _onJellyfinUserActionSelected(self, choice):
		uid = getattr(self, '_pendingJellyfinUserUid', None)
		self._pendingJellyfinUserUid = None
		if not choice or not uid:
			return
		_label, action = choice
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return

		if action == "switch":
			self._startJellyfinSwitch(user)
		elif action == "set_pin":
			self._pendingPinTargetUid = uid
			self.session.openWithCallback(self._onNewJellyfinUserPinEntered, InputBox, title=_("Choose a pincode for this profile"), type=Input.PIN)
		elif action == "change_pin":
			self._pendingPinTargetUid = uid
			self.session.openWithCallback(self._onChangePinOldEntered, InputBox, title=_("Enter the current pincode"), type=Input.PIN)
		elif action == "remove_pin":
			self._pendingPinTargetUid = uid
			self.session.openWithCallback(self._onRemovePinEntered, InputBox, title=_("Enter the current pincode to remove it"), type=Input.PIN)

	#==========================================================================
	# Switching to a saved user - decrypts token/password if the profile is
	# PIN-protected, migrating a plaintext token/password left over from
	# before this profile had a PIN to an encrypted one on the fly.
	#==========================================================================
	def _startJellyfinSwitch(self, user):
		if self._hasPin(user):
			self._pendingJellyfinUserUid = user.id.getValue()
			self.session.openWithCallback(self._onJellyfinSwitchPinEntered, InputBox, title=_("Please enter the pincode!"), type=Input.PIN)
		else:
			self._performJellyfinUserSwitch(user.id.getValue(), user.username.getValue(), user.token.getValue(), user.password.getValue(), None)

	def _onJellyfinSwitchPinEntered(self, entered):
		uid = getattr(self, '_pendingJellyfinUserUid', None)
		self._pendingJellyfinUserUid = None
		if entered is None or not uid:
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return
		pin = str(entered)
		rawToken = user.token.getValue()
		rawPassword = user.password.getValue()

		if DPH_Vault.isEncrypted(rawToken):
			# the only correctness check there is: does this pin actually
			# decrypt the token (HMAC tag verified inside DPH_Vault.decrypt).
			# No plaintext pin is compared anywhere in this branch.
			token = DPH_Vault.decrypt(rawToken, pin)
			password = DPH_Vault.decrypt(rawPassword, pin) if DPH_Vault.isEncrypted(rawPassword) else rawPassword
			if token is None:
				self.session.open(MessageBox, _("Wrong pincode!"), MessageBox.TYPE_INFO)
				return
		else:
			# legacy profile from before token/password encryption existed:
			# token is still plaintext, so the only thing to check against is
			# the plaintext pin field left over from that build. Once
			# verified, migrate to real encryption and blank that field -
			# this is the last time this plugin ever compares a plaintext pin.
			storedPin = user.pin.getValue()
			if str(pin) != str(storedPin):
				self.session.open(MessageBox, _("Wrong pincode!"), MessageBox.TYPE_INFO)
				return
			token = rawToken
			password = rawPassword
			try:
				user.token.setValue(DPH_Vault.encrypt(rawToken, pin))
				if rawPassword:
					user.password.setValue(DPH_Vault.encrypt(rawPassword, pin))
				user.pin.setValue("")
				self.g_serverConfig.saveChanges()
			except Exception as e:
				printl("could not migrate plaintext token to encrypted: " + str(e), self, "W")

		self._performJellyfinUserSwitch(uid, user.username.getValue(), token, password, pin)

	def _performJellyfinUserSwitch(self, uid, username, token, password=None, pin=None):
		try:
			# Salva su settings correnti e aggiorna header
			if hasattr(self.g_serverConfig, '_userId'):
				self.g_serverConfig._userId.setValue(uid)
			if hasattr(self.g_serverConfig, '_username'):
				self.g_serverConfig._username.setValue(username)
			if hasattr(self.g_serverConfig, '_accessToken'):
				self.g_serverConfig._accessToken.setValue(token)
			try:
				self.g_serverConfig.saveChanges()
			except Exception:
				pass
			# Aggiorna header token nella media library, e tiene in memoria
			# (mai su disco) il pin/password di questa sessione: servono a
			# JellyfinLibrary._tryRefreshToken() per rifare il login da solo
			# se il token scade, senza doverlo chiedere di nuovo all'utente.
			try:
				self.mediaLibraryInstance.setAccessTokenHeader(self.mediaLibraryInstance.g_currentServer, token)
				self.mediaLibraryInstance._sessionPin = pin
				self.mediaLibraryInstance._sessionPassword = password
			except Exception:
				pass
			self["text_HomeUser"].setText(username)
			self.session.open(MessageBox, _("User switched"), MessageBox.TYPE_INFO)
		except Exception as e:
			self.session.open(MessageBox, _("Error:") + "\n" + str(e), MessageBox.TYPE_ERROR)

	#==========================================================================
	# Setting / changing / removing a profile's PIN
	#==========================================================================
	def _onNewJellyfinUserPinEntered(self, entered):
		uid = getattr(self, '_pendingPinTargetUid', None)
		self._pendingPinTargetUid = None
		if entered is None or not uid:
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return
		pin = str(entered)
		try:
			token = user.token.getValue()
			password = user.password.getValue()
			if token:
				user.token.setValue(DPH_Vault.encrypt(token, pin))
			if password:
				user.password.setValue(DPH_Vault.encrypt(password, pin))
			# no plaintext pin is stored anywhere - isEncrypted(token) is
			# what _hasPin() checks from now on
			self.g_serverConfig.saveChanges()
			# if this is the profile currently active this session, keep the
			# in-memory pin in sync too, so a token refresh right after
			# setting the pin does not have to ask for it again
			if self.g_serverConfig._userId.getValue() == uid:
				self.mediaLibraryInstance._sessionPin = pin
			self.session.open(MessageBox, _("PIN set for this profile"), MessageBox.TYPE_INFO)
		except Exception as e:
			self.session.open(MessageBox, _("Error:") + "\n" + str(e), MessageBox.TYPE_INFO)

	def _onChangePinOldEntered(self, entered):
		uid = getattr(self, '_pendingPinTargetUid', None)
		if entered is None or not uid:
			self._pendingPinTargetUid = None
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			self._pendingPinTargetUid = None
			return
		rawToken = user.token.getValue()
		# same rule as everywhere else: correct is whatever actually
		# decrypts the token, plaintext-pin comparison only survives as the
		# one-time legacy migration path
		if DPH_Vault.isEncrypted(rawToken):
			ok = DPH_Vault.decrypt(rawToken, str(entered)) is not None
		else:
			ok = str(entered) == str(user.pin.getValue())
		if not ok:
			self._pendingPinTargetUid = None
			self.session.open(MessageBox, _("Wrong pincode!"), MessageBox.TYPE_INFO)
			return
		self._pendingOldPin = str(entered)
		# _pendingPinTargetUid stays set for the next step
		self.session.openWithCallback(self._onChangePinNewEntered, InputBox, title=_("Enter the new pincode"), type=Input.PIN)

	def _onChangePinNewEntered(self, entered):
		uid = getattr(self, '_pendingPinTargetUid', None)
		oldPin = getattr(self, '_pendingOldPin', None)
		self._pendingPinTargetUid = None
		self._pendingOldPin = None
		if entered is None or not uid or not oldPin:
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return
		newPin = str(entered)
		try:
			rawToken = user.token.getValue()
			rawPassword = user.password.getValue()
			token = DPH_Vault.decrypt(rawToken, oldPin) if DPH_Vault.isEncrypted(rawToken) else rawToken
			password = DPH_Vault.decrypt(rawPassword, oldPin) if DPH_Vault.isEncrypted(rawPassword) else rawPassword
			if token is None:
				self.session.open(MessageBox, _("Wrong pincode!"), MessageBox.TYPE_INFO)
				return
			user.token.setValue(DPH_Vault.encrypt(token, newPin))
			if password:
				user.password.setValue(DPH_Vault.encrypt(password, newPin))
			user.pin.setValue("")  # stale legacy field, if this profile still had one
			self.g_serverConfig.saveChanges()
			self.session.open(MessageBox, _("PIN changed"), MessageBox.TYPE_INFO)
		except Exception as e:
			self.session.open(MessageBox, _("Error:") + "\n" + str(e), MessageBox.TYPE_INFO)

	def _onRemovePinEntered(self, entered):
		uid = getattr(self, '_pendingPinTargetUid', None)
		self._pendingPinTargetUid = None
		if entered is None or not uid:
			return
		user = self._jellyfinUserByUid(uid)
		if user is None:
			return
		pin = str(entered)
		try:
			rawToken = user.token.getValue()
			rawPassword = user.password.getValue()
			if DPH_Vault.isEncrypted(rawToken):
				token = DPH_Vault.decrypt(rawToken, pin)
			else:
				# legacy plaintext-token profile: the only thing left to
				# check against is the old plaintext pin field
				token = rawToken if pin == str(user.pin.getValue()) else None
			password = DPH_Vault.decrypt(rawPassword, pin) if DPH_Vault.isEncrypted(rawPassword) else rawPassword
			if token is None:
				self.session.open(MessageBox, _("Wrong pincode!"), MessageBox.TYPE_INFO)
				return
			user.token.setValue(token)
			user.password.setValue(password or "")
			user.pin.setValue("")
			self.g_serverConfig.saveChanges()
			self.session.open(MessageBox, _("PIN removed"), MessageBox.TYPE_INFO)
		except Exception as e:
			self.session.open(MessageBox, _("Error:") + "\n" + str(e), MessageBox.TYPE_INFO)

	def askJellyfinUsername(self):
		try:
			self.session.openWithCallback(self._onJellyfinUsernameEntered, DPS_TextInputBox, title=_("Enter Jellyfin username"), type=Input.TEXT)
		except Exception:
			# Fallback: semplicemente non fare nulla
			pass

	def _onJellyfinUsernameEntered(self, username):
		if username is None or username == "":
			return
		self._jellyfin_username_tmp = username
		try:
			self.session.openWithCallback(self._onJellyfinPasswordEntered, DPS_TextInputBox, title=_("Enter Jellyfin password"), type=Input.TEXT)
		except Exception:
			pass

	def _onJellyfinPasswordEntered(self, password):
		if password is None:
			return
		# Autentica tramite settings Jellyfin
		try:
			ok, info = self.g_serverConfig.authenticateUser(self.session, self._jellyfin_username_tmp, password)
			if ok:
				token = info.get(AuthorizationResult.CREDENTIALS)
				# Aggiorna header e UI
				try:
					if token:
						self.mediaLibraryInstance.setAccessTokenHeader(self.mediaLibraryInstance.g_currentServer, token)
						self.mediaLibraryInstance._sessionPin = None
						self.mediaLibraryInstance._sessionPassword = password
				except Exception:
					pass
				self["text_HomeUser"].setText(self._jellyfin_username_tmp)
				try:
					self.g_serverConfig.saveChanges()
				except Exception:
					pass
				self._newJellyfinUserId = info.get(AuthorizationResult.ID)
				self.session.openWithCallback(self._onAskProtectJellyfinUser, MessageBox,
					_("Login successful.\n\nProtect this profile with a PIN before switching to it later?"), MessageBox.TYPE_YESNO)
			else:
				msg = info.get(AuthorizationResult.ERROR) if isinstance(info, dict) else _("Login failed")
				self.session.open(MessageBox, _("Error:") + "\n" + str(msg), MessageBox.TYPE_INFO)
		except Exception as e:
			self.session.open(MessageBox, _("Error:") + "\n" + str(e), MessageBox.TYPE_INFO)

	def _onAskProtectJellyfinUser(self, answer):
		userId = getattr(self, '_newJellyfinUserId', None)
		self._newJellyfinUserId = None
		if not answer or not userId:
			return
		self._pendingPinTargetUid = userId
		self.session.openWithCallback(self._onNewJellyfinUserPinEntered, InputBox, title=_("Choose a pincode for this profile"), type=Input.PIN)

	#===========================================================================
	#
	#===========================================================================
	def displayOptionsMenuCallback(self, choice):
		printl("", self, "S")

		if choice is None or choice[1] is None:
			printl("choice: None - we pressed exit", self, "D")
			return

		printl("choice: " + str(choice), self, "D")
		self.isHomeUser = choice[3]
		self.currentHomeUserId = choice[4]
		self.currentHomeUserPin = choice[1]

		if self.isHomeUser:
			if choice[1] != "":
				printl(choice[1], self, "D")
				self.session.openWithCallback(self.askForPin, InputBox, title=_("Please enter the pincode!"), type=Input.PIN)
			else:
				self.switchUser()
		else:
			if self.g_serverConfig.myplexPinProtect().getValue():
				self.session.openWithCallback(self.askForPin, InputBox, title=_("Please enter the pincode!"), type=Input.PIN)
				self.currentPin = self.g_serverConfig.myplexPin().getValue()
			else:
				self.switchUser()

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def switchUser(self):
		printl("", self, "S")

		# TODO add use saved values if we have no internet connection

		xmlResponse = self.mediaLibraryInstance.switchUser(self.currentHomeUserId, self.currentHomeUserPin)

		entryData = (dict(xmlResponse.items()))
		myId = entryData['id']
		token = entryData['authenticationToken']
		title = entryData['title']

		self.mediaLibraryInstance.serverConfig_myplexToken = token
		accessToken = self.mediaLibraryInstance.getUserTokenForLocalServerAuthentication(self.mediaLibraryInstance.g_host)

		if not accessToken:
			# we get all the restriction data from plex and not from the local server this means that if we ar not connected no data is coming to check, means no restction
			self.session.open(MessageBox, "No accessToken! Check plex.tv connection and plexPass status.", MessageBox.TYPE_INFO)
		else:
			self.g_serverConfig.myplexCurrentHomeUser().setValue(title)
			self.g_serverConfig.myplexCurrentHomeUserAccessToken().setValue(accessToken)
			self.g_serverConfig.myplexCurrentHomeUserId().setValue(myId)
			self.g_serverConfig.saveChanges()

			self.mediaLibraryInstance.setAccessTokenHeader(self.mediaLibraryInstance.g_currentServer, accessToken)

			self["text_HomeUser"].setText(title)

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def askForPin(self, enteredPin):
		printl("", self, "S")

		if enteredPin is None:
			pass
		else:
			if int(enteredPin) == int(self.currentPin):
				self.session.open(MessageBox, "The pin was correct! Switching user.", MessageBox.TYPE_INFO)
				#				if self.isHomeUser:
				#					self.switchUser()
				#				else:
				self.switchUser()
			else:
				self.session.open(MessageBox, "The pin was wrong! Abort user switiching.", MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===============================================================
	#
	#===============================================================
	def okbuttonClick(self):
		printl("", self, "S")

		if self._heroEnabled and self._heroFocused:
			self._playHeroItem()
			printl("", self, "C")
			return

		# Defensive: any real interaction with the sidebar list itself
		# (drilling into a submenu, here) means the user is not looking at
		# the hero banner any more, regardless of how focus got left in
		# whatever state it was in - avoids a "stuck" _heroFocused causing
		# a later OK to unexpectedly play the hero instead of the sidebar
		# selection.
		if self._heroEnabled:
			self._heroFocused = False

		self.currentMenuDataDict[self.menuStep] = self.g_serverDataMenu
		printl("currentMenuDataDict: " + str(self.currentMenuDataDict), self, "D")

		# first of all we save the data from the current step
		self.currentIndexDict[self.menuStep] = self["menu"].getIndex()

		# now we increase the step value because we go to the next step
		self.menuStep += 1
		printl("menuStep: " + str(self.menuStep), self, "D")

		# this is used to step in directly into a server when there is only one entry in the serverlist
		if self.selectionOverride is not None:
			selection = self.selectionOverride

			# because we change the screen we have to unset the information to be able to return to main menu
			self.selectionOverride = None
		else:
			selection: SelectionItem = self["menu"].getCurrent()

		printl("selection = " + str(selection), self, "D")

		if selection is not None and selection:

			self.selectedEntry = selection[1]
			printl("selected entry " + str(self.selectedEntry), self, "D")

			if type(self.selectedEntry) is int:
				printl("selected entry is int", self, "D")

				if self.selectedEntry == Plugin.MENU_MOVIES:
					printl("found Plugin.MENU_MOVIES", self, "D")
					self.getServerData("movies")

				elif self.selectedEntry == Plugin.MENU_TVSHOWS:
					printl("found Plugin.MENU_TVSHOWS", self, "D")
					self.getServerData("tvshow")

				elif self.selectedEntry == Plugin.MENU_MUSIC:
					printl("found Plugin.MENU_MUSIC", self, "D")
					self.getServerData("music")

				elif self.selectedEntry == Plugin.MENU_FILTER:
					printl("found Plugin.MENU_FILTER", self, "D")
					self.getFilterData(selection[3])

				elif self.selectedEntry == Plugin.MENU_SERVERFILTER:
					self.getServerData(filterBy=selection[3]['myCurrentFilterData'], serverFilterActive=selection[3]['serverName'])

			else:
				printl("selected entry is executable", self, "D")
				self.mediaType = selection[2]
				printl("mediaType: " + str(self.mediaType), self, "D")

				entryData = selection[3]
				printl("entryData: " + str(entryData), self, "D")

				# Gestione prompt standard (Plex) e avanzato (Jellyfin)
				# Jellyfin: se presente 'jellyfinPrompt' apriamo un InputBox dedicato
				if isinstance(entryData, dict) and entryData.get('jellyfinPrompt'):
					if self._openJellyfinPrompt(entryData):
						return
				hasPromptTag = entryData.get('hasPromptTag', False)
				printl("hasPromptTag: " + str(hasPromptTag), self, "D")
				if hasPromptTag:
					self.session.openWithCallback(self.addSearchString, DPS_InputBox, entryData, title=_("Please enter your search string: "), text=" " * 55, maxSize=55, type=Input.TEXT)
				else:
					self.menuStep -= 1
					self.executeSelectedEntry(entryData)

			self.refreshMenu()
		else:
			printl("no data, leaving ...", self, "D")
			self.cancel()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def addSearchString(self, entryData, searchString=None):
		printl("", self, "S")
		printl("entryData: " + str(entryData), self, "D")

		if searchString is not None:
			if "origContentUrl" in entryData[0]:
				searchUrl = entryData[0]["origContentUrl"] + "&query=" + searchString
			else:
				searchUrl = entryData[0]["contentUrl"] + "&query=" + searchString
				entryData[0]["origContentUrl"] = entryData[0]["contentUrl"]

			printl("searchUrl: " + str(searchUrl), self, "D")

			entryData[0]["contentUrl"] = searchUrl

		self.executeSelectedEntry(entryData[0])

		printl("", self, "C")

	#===========================================================================
	# this function starts DP_Lib...
	#===========================================================================
	def executeSelectedEntry(self, entryData):
		printl("", self, "S")

		if self.selectedEntry.start is not None:
			printl("we are startable ...", self, "D")
			self.session.openWithCallback(self.myCallback, self.selectedEntry.start, entryData)

		elif self.selectedEntry.fnc is not None:
			printl("we are a function ...", self, "D")
			self.selectedEntry.fnc(self.session)

		if self.settings.showFilter.getValue():
			self.selectedEntry = Plugin.MENU_FILTER  # we overwrite this now to handle correct menu jumps with exit/cancel button

		printl("", self, "C")

	#==========================================================================
	# Jellyfin: gestione prompt per filtri avanzati (genere/anno/ricerca)
	#==========================================================================
	def _openJellyfinPrompt(self, entryData):
		try:
			jfprompt = entryData.get('jellyfinPrompt')
		except Exception:
			jfprompt = None
		if not jfprompt:
			return False

		self._jfprompt_type = jfprompt
		self._jfprompt_data = entryData

		if jfprompt == 'genre':
			title = _("Enter genre(s), comma separated")
		elif jfprompt == 'year':
			title = _("Enter year(s), comma separated")
		else:
			title = _("Enter search text")

		try:
			self.session.openWithCallback(self._onJellyfinPromptEntered, DPS_TextInputBox, title=title, type=Input.TEXT)
		except Exception:
			pass
		return True

	def _onJellyfinPromptEntered(self, value):
		# Se annullato, torna indietro di uno step e non fare nulla
		if value is None:
			self.menuStep -= 1
			return
		try:
			data = dict(self._jfprompt_data)
		except Exception:
			data = {}

		jfprompt = getattr(self, '_jfprompt_type', None)
		if jfprompt == 'genre':
			genres = [g.strip() for g in str(value).split(',') if g.strip()]
			data['genres'] = genres
		elif jfprompt == 'year':
			years = []
			for y in str(value).split(','):
				y = y.strip()
				if y.isdigit():
					years.append(int(y))
			data['years'] = years if years else str(value)
		elif jfprompt == 'rating':
			# accetta singolo valore o range "min-max"
			txt = str(value).replace(',', '-').strip()
			if '-' in txt:
				parts = txt.split('-')
				try:
					data['ratingMin'] = float(parts[0])
				except Exception:
					pass
				try:
					data['ratingMax'] = float(parts[1])
				except Exception:
					pass
			else:
				try:
					data['rating'] = float(txt)
				except Exception:
					pass
		elif jfprompt == 'runtime':
			# minuti o range "min-max" in minuti → converti in ticks (1s=10^7)
			def _m_to_ticks(m):
				try:
					return int(float(m) * 60 * 10_000_000)
				except Exception:
					return None
			txt = str(value).replace(',', '-').strip()
			if '-' in txt:
				parts = txt.split('-')
				lo = _m_to_ticks(parts[0])
				hi = _m_to_ticks(parts[1])
				if lo is not None:
					data['runtimeMinTicks'] = lo
				if hi is not None:
					data['runtimeMaxTicks'] = hi
			else:
				ticks = _m_to_ticks(txt)
				if ticks is not None:
					data['runtimeMinTicks'] = ticks
		else:
			data['searchTerm'] = str(value)

		# Rimuovi il flag di prompt per evitare loop
		if 'jellyfinPrompt' in data:
			try:
				del data['jellyfinPrompt']
			except Exception:
				pass
		# data started as a shallow copy of self._jfprompt_data, so its
		# "contentUrl" still points at the *original* dict (without the
		# genres/years/searchTerm/rating/runtime just added above) - repoint
		# it at this dict so DP_LibMain.loadLibraryData() picks up the
		# user-entered filter, not the stale one.
		data['contentUrl'] = data
		# Go back one step and issue the filtered request
		self.menuStep -= 1
		self.executeSelectedEntry(data)

	#==========================================================================
	#
	#==========================================================================
	def myCallback(self, *args):
		printl("", self, "S")

		# *args: shared between two different callers with different close()
		# shapes - self.selectedEntry.start (no return value) and DP_Player
		# (always closes with one positional tuple, e.g. from
		# leavePlayerConfirmed()/exitFunction()). Its content is not needed
		# here, only that the decoder is free again.
		if not self.settings.stopLiveTvOnStartup.getValue():
			self.session.nav.playService(getLiveTv(), forceRestart=True)

		printl("", self, "C")

	#===========================================================================
	# Same reasoning as DP_MainMenu._onShortcut()/._appendShortcutLabels():
	# digit N jumps straight to row N of whatever is currently in "menu"
	# (getSectionTypes()/getAllSections()/getSectionFilter() results, all
	# already-built 5-tuple listing rows - the label is appended as a 6th,
	# trailing element so every existing selection[1]/[2]/[3] index access
	# stays correct). Rows beyond the 9th simply get no shortcut.
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

	# Same fixed-index-via-padding reasoning as DP_MainMenu._appendShortcutLabels()
	# - padTo=5 matches the (title, entryData, contextMenu, viewState,
	# nextUrl) shape every listing row already uses in this codebase, so the
	# label lands at index 5 for all of them; the padding is a no-op unless
	# a row somehow arrives shorter than that.
	def _appendShortcutLabels(self, menuList, padTo=5):
		result = []
		for i, row in enumerate(menuList):
			row = tuple(row)
			if len(row) < padTo:
				row = row + (None,) * (padTo - len(row))
			result.append(row + (str(i + 1) if i < 9 else "",))
		return result

	#==========================================================================
	#
	#==========================================================================
	def up(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			self.left()
		elif self._heroEnabled and self._heroFocused:
			# Leaving the hero banner from the top - back to the sidebar,
			# the reverse of down()'s "fall into the hero past the last row".
			self._setHeroFocused(False)
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
		elif self._heroEnabled and self._heroCandidates and not self._heroFocused and self["menu"].getIndex() >= len(self["menu"].list) - 1:
			# Already on the last sidebar row - DOWN "falls through" onto the
			# hero banner below it, instead of doing nothing (selectNext()
			# has nowhere further to go there anyway). Mnemonic: the hero
			# sits visually below the list, so reaching it by continuing
			# down is the natural gesture - RIGHT used to do this instead,
			# which silently ate the "enter a submenu" key every time the
			# hero was present (see right()).
			self._setHeroFocused(True)
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
			# RIGHT now mirrors OK (enter the highlighted row / play the
			# hero if it has focus) instead of paging or silently stealing
			# the key to focus the hero - paging was already a no-op on
			# this screen's short sidebar-level lists (same reasoning as
			# LEFT's fallback below), and hijacking "enter" for hero-focus
			# was exactly what made Right/Left feel broken for real menu
			# navigation. The hero is now reached via DOWN/UP instead.
			self.okbuttonClick()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def left(self):
		printl("", self, "S")

		if self._heroEnabled and self._heroFocused:
			self._setHeroFocused(False)
			printl("", self, "C")
			return

		if self.g_horizontal_menu:
			try:
				self.refreshOrientationHorMenu(-1)
			except Exception as ex:
				printl("Exception(" + str(type(ex)) + "): " + str(ex), self, "W")
				self["menu"].selectPrevious()
		else:
			# Unlike DP_View's genre/movie lists (which show a real
			# "Pagine: X/Y" and where pageUp() is meaningful mid-list),
			# this screen's own sidebar levels have no such concept -
			# pageUp() here was always effectively a no-op. LEFT falls
			# straight through to going back a level instead, the missing
			# counterpart to the "Sinistra oltre la prima pagina torna
			# indietro" rule already implemented for DP_View
			# (onPreviousPage()).
			self.cancel()

		printl("", self, "C")

	#===========================================================================
	# Hero banner: focus toggle, fetch/rotation timer, and play.
	#===========================================================================
	def _setHeroFocused(self, focused):
		self._heroFocused = focused
		# Pause rotation while the user is looking at/deciding on the
		# current suggestion - resumed automatically on the next tick once
		# focus returns to the sidebar (the timer itself keeps running; a
		# focused tick just re-arms without advancing, see _onHeroTimerTick()).
		if not self._heroCandidates:
			return
		self._updateHeroDisplay()

	def _fetchHeroCandidates(self):
		printl("", self, "S")

		try:
			candidates = self.mediaLibraryInstance.getHeroSuggestions(limit=self.settings.heroMaxItems.getValue()) or []
			# Neither backend's getHeroSuggestions() filters out containers.
			# type != 'Folder' (the first attempt at this) only catches raw
			# filesystem folders - live-tested with a real log: a Jellyfin
			# "Series" row from the Latest/Resume endpoints (a whole TV show,
			# not an episode) has type 'Series', not 'Folder', and sailed
			# right through. tagType is the one field both backends already
			# normalize to "Video"/"Track" for an actually playable leaf
			# (Movie/Episode/Audio - see JellyfinLibrary._LEAF_TAG_TYPES, and
			# DP_PlexLibrary hardcodes "Video" for the same reason) and to
			# the raw, backend-specific container type name (Series, Season,
			# BoxSet, Playlist, Folder, ...) for anything else - a container
			# has a title/poster/plot like any other row (which is why
			# DP_Player still showed something), but no playable media of
			# its own, so playback silently never started.
			#
			# 'Series' is the one container type kept anyway: a whole show
			# suggested via Latest/Resume is still a meaningful suggestion -
			# _playHeroItem() opens its season/episode browser instead of
			# trying to play it directly (see there). Any other container
			# (Season, BoxSet, Playlist, a raw folder, ...) is dropped, same
			# as before - not common enough from these two endpoints to be
			# worth a bespoke landing screen each.
			self._heroCandidates = [c for c in candidates if c[1].get('tagType') in ('Video', 'Track', 'Series')]
		except Exception as ex:
			printl("could not fetch hero suggestions: " + str(ex), self, "W")
			self._heroCandidates = []

		self._heroIndex = 0
		self._heroLoopCount = 0

		if self._heroCandidates:
			self._updateHeroDisplay()

		interval = self.settings.heroRotationInterval.getValue()
		self._heroTimer.stop()
		if interval > 0:
			self._heroTimer.start(interval * 1000, True)
		self._armHeroCountdown(interval * 1000)

		printl("", self, "C")

	def _onHeroTimerTick(self):
		if not self._heroFocused and self._heroCandidates:
			self._heroIndex += 1
			if self._heroIndex >= len(self._heroCandidates):
				self._heroIndex = 0
				self._heroLoopCount += 1
				if self._heroLoopCount >= self.settings.heroRefetchAfterLoops.getValue():
					self._fetchHeroCandidates()
					return  # _fetchHeroCandidates() already re-armed the timer/countdown
			self._updateHeroDisplay()

		interval = self.settings.heroRotationInterval.getValue()
		if interval > 0:
			self._heroTimer.start(interval * 1000, True)
		self._armHeroCountdown(interval * 1000)

	def _stopHeroTimer(self):
		if self._heroEnabled:
			self._heroTimer.stop()
			self._heroProgressTimer.stop()

	#===========================================================================
	# Countdown bar: (re)armed every time the rotation timer itself is (re)armed,
	# so it always reflects the real time left until the next tick - regardless
	# of whether that tick ends up advancing the hero (paused while focused, see
	# _onHeroTimerTick()). Ticks on its own short interval for a smooth-looking
	# animation instead of jumping once per rotation interval.
	#===========================================================================
	def _armHeroCountdown(self, intervalMs):
		self._heroIntervalTotalMs = intervalMs
		self._heroElapsedMs = 0
		self._heroProgressTimer.stop()
		if intervalMs > 0:
			self["heroProgress"].setValue(100)
			self["heroProgress"].show()
			self._heroProgressTimer.start(200, False)
		else:
			self["heroProgress"].hide()

	def _onHeroProgressTick(self):
		total = self._heroIntervalTotalMs
		if total <= 0:
			self["heroProgress"].hide()
			self._heroProgressTimer.stop()
			return
		self._heroElapsedMs += 200
		percent = max(0, 100 - int(self._heroElapsedMs * 100 / total))
		self["heroProgress"].setValue(percent)

	def _updateHeroDisplay(self):
		if not self._heroCandidates:
			return

		title, entryData, _cm, _vs, _nu = self._heroCandidates[self._heroIndex]

		parts = []
		year = entryData.get('year')
		if year:
			parts.append(str(year))
		genre = entryData.get('genre')
		if genre:
			parts.append(str(genre))
		rating = entryData.get('rating')
		try:
			if rating:
				parts.append("★ %.1f" % float(rating))
		except (TypeError, ValueError):
			pass

		displayTitle = title
		if len(self._heroCandidates) > 1:
			displayTitle = "%d/%d   %s" % (self._heroIndex + 1, len(self._heroCandidates), title)
		if self._heroFocused:
			displayTitle = "▶ " + displayTitle

		if self._heroFocused:
			self["heroFocusFrame"].show()
		else:
			self["heroFocusFrame"].hide()

		# getHeroSuggestions() tags every candidate 'continue' (in progress/
		# next up) or 'suggested' (recently added) - shown here so a title
		# already started is not confused for a fresh recommendation. A
		# whole show (tagType 'Series', see _fetchHeroCandidates()/
		# _playHeroItem()) gets its own badge instead, replacing continue/
		# suggested entirely - which bucket it came from matters less here
		# than "OK/BLUE opens this, it will not start playing".
		if entryData.get('tagType') == 'Series':
			self["heroKindBadge"].setText(_("Open series"))
		elif entryData.get('heroKind') == 'continue':
			self["heroKindBadge"].setText(_("Continue watching"))
		else:
			self["heroKindBadge"].setText(_("Suggested"))

		self["heroTitle"].setText(displayTitle)
		self["heroMeta"].setText("   •   ".join(parts))

		# heroSummary is a plain Label (no scrolling, unlike DP_Player's
		# carousel which has UP/DOWN free for that) - UP/DOWN here already
		# do sidebar navigation / hero focus toggle, so a long summary is
		# truncated with an ellipsis instead of silently overflowing past
		# the widget's bottom edge (what was happening before).
		summary = entryData.get('summary') or entryData.get('overview') or ""
		maxChars = 320
		if len(summary) > maxChars:
			summary = summary[:maxChars].rsplit(' ', 1)[0] + "…"
		self["heroSummary"].setText(summary)

		posterPtr = self._loadHeroPoster(entryData)
		if posterPtr is not None:
			self["heroPoster"].instance.setPixmap(posterPtr)
			self["heroPoster"].show()

		# A show has nothing of its own to play - BLUE/OK open its season/
		# episode browser instead (see _playHeroItem()), so the hint has to
		# say so, not promise "Play".
		if entryData.get('tagType') == 'Series':
			self["btn_blueText"].setText(_("Browse"))
		else:
			self["btn_blueText"].setText(_("Play"))
		self["btn_blue"].show()
		self["btn_blueText"].show()

	#===========================================================================
	# Downloads (once per item, cached on disk) and decodes the poster for
	# the currently-shown hero suggestion - same synchronous, one-off
	# pattern as DP_Player._loadSimilarSuggestionPoster(), reused here
	# rather than duplicated logic invented from scratch.
	#===========================================================================
	def _loadHeroPoster(self, entryData):
		itemId = entryData.get('ratingKey') or entryData.get('id') or ''
		downloadUrl = entryData.get('thumb') or ''
		if not itemId or not downloadUrl:
			return None

		try:
			imagePrefix = self.mediaLibraryInstance.getServerName().lower()
			widget = self["heroPoster"]
			w, h = widget.instance.size().width(), widget.instance.size().height()
			posterPath = self.settings.mediaFolderPath.getValue() + imagePrefix + "_hero_" + str(itemId) + "_" + str(w) + "x" + str(h) + ".jpg"

			if not fileExists(posterPath):
				downloadUrl = downloadUrl.replace('&width=999&height=999', '&width=%d&height=%d' % (w, h))
				response = self.mediaLibraryInstance.doRequest(downloadUrl)
				with open(posterPath, "wb") as local_file:
					local_file.write(response)

			self._heroPicLoad.setPara([w, h, self._heroScale[0], self._heroScale[1], 0, 1, "#002C2C39"])
			self._heroPicLoad.startDecode(posterPath, 0, 0, False)
			return self._heroPicLoad.getData()
		except Exception as e:
			printl("could not load hero poster: " + str(e), self, "W")
			return None

	#===========================================================================
	# OK while the hero has focus plays it directly, the same way DP_Player's
	# "you might also like" carousel does (_playSimilarSuggestion()) - a
	# single-item listViewList rather than splicing into any real playlist.
	#===========================================================================
	def onKeyBlue(self):
		printl("", self, "S")

		if self._heroEnabled and self._heroCandidates:
			self._playHeroItem()

		printl("", self, "C")

	def _playHeroItem(self):
		printl("", self, "S")

		if not self._heroCandidates:
			printl("", self, "C")
			return

		entry = self._heroCandidates[self._heroIndex]
		title, entryData, contextMenu, viewState, nextUrl = entry

		# A whole show (see _fetchHeroCandidates()'s tagType filter) has
		# nothing of its own to play - land on its season/episode browser
		# instead, the same screen "TV Shows" from the sidebar opens, just
		# pre-seeded to this one show instead of the top-level list. Mirrors
		# what DP_View.onEnter() does for any non-leaf row: contentUrl is
		# never set on entryData until the row is actually entered (see
		# JellyfinLibrary._to_entry()/DP_PlexLibrary.getFullListEntry()).
		if entryData.get('tagType') == 'Series':
			entryData['contentUrl'] = nextUrl
			self.session.openWithCallback(self.myCallback, DP_LibShows, entryData)
			printl("", self, "C")
			return

		# openWithCallback + myCallback (not a plain open()): DP_Player takes
		# over decoder 0 for real playback, the same decoder self["miniTv"]
		# uses to show live TV in the corner (see DPH_ScreenHelper). Every
		# other screen here that can grab the decoder (see
		# executeSelectedEntry() above) already restores live TV through
		# myCallback once it closes - this was the one path that opened
		# DP_Player directly and skipped it, which is what left the miniTV
		# frozen on a black frame after leaving the player, until the next
		# full re-entry into this screen reinitialized it from scratch.
		self.session.openWithCallback(self.myCallback, DP_Player, [entry], 0, "mixed", False, True, self.g_serverConfig.playbackType().getValue(), autoSelectFirstMedia=True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def exit(self):
		printl("", self, "S")

		self.close((True,))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def cancel(self):
		printl("", self, "S")

		if self._heroEnabled:
			self._heroFocused = False

		self.menuStep -= 1
		printl("menuStep: " + str(self.menuStep), self, "D")

		if self.menuStep >= 0:
			self.g_serverDataMenu = self.currentMenuDataDict[self.menuStep]
			self["menu"].setList(self.g_serverDataMenu)
			self.beforeFilterListViewList = self.g_serverDataMenu
			self["menu"].setIndex(self.currentIndexDict[self.menuStep])
			self.refreshMenu()
		else:
			self.exit()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def refreshMenu(self):
		printl("", self, "S")

		if self.g_horizontal_menu:
			self.refreshOrientationHorMenu(0)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getServerData(self, filterBy=None, serverFilterActive=False):
		printl("", self, "S")

		if self.settings.summerizeSections.getValue() and filterBy is None:
			serverData = self.mediaLibraryInstance.getSectionTypes()
		else:
			serverData = self.mediaLibraryInstance.getAllSections(myFilter=filterBy, serverFilterActive=serverFilterActive)

		if not serverData:
			self.showNoDataMessage()
		else:
			serverData = self._appendShortcutLabels(serverData)
			self.g_serverDataMenu = serverData  # lets save the menu to call it when cancel is pressed

			self["menu"].setList(serverData)
			self.beforeFilterListViewList = self.g_serverDataMenu
			self.refreshMenu()
			try:
				self["menu"].top()
			except Exception:
				try:
					self["menu"].setIndex(0)
				except Exception:
					pass

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getFilterData(self, entryData):
		printl("", self, "S")
		menuData = self.mediaLibraryInstance.getSectionFilter(entryData)

		if not menuData:
			self.showNoDataMessage()
			self.menuStep -= 1
			printl("menuStep: " + str(self.menuStep), self, "D")

		else:
			menuData = self._appendShortcutLabels(menuData)
			self["menu"].setList(menuData)
			self.g_serverDataMenu = menuData  # lets save the menu to call it when cancel is pressed
			self.beforeFilterListViewList = self.g_serverDataMenu
			self.refreshMenu()

		printl("", self, "S")

	#===========================================================================
	#
	#===========================================================================
	def showNoDataMessage(self):
		printl("", self, "S")

		text = self.mediaLibraryInstance.getLastErrorMessage()
		self.session.open(MessageBox, _("\n%s") % text, MessageBox.TYPE_INFO)

		printl("", self, "C")
