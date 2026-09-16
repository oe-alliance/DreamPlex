# -*- coding: utf-8 -*-
"""
"""
from __future__ import annotations
import itertools
import threading
from abc import ABC, abstractmethod
from xml.etree.ElementTree import Element

from typing import Generic, TypeVar, Type, Any, Union, TYPE_CHECKING
from enum import Enum

from Components.config import ConfigElement, ConfigYesNo, ConfigDirectory, ConfigText, ConfigSelection, \
	ConfigSubsection, ConfigInteger, ConfigPassword, ConfigPIN, ConfigIP, getConfigListEntry
from .__common__ import EntryServer, DiscoveredServer, printl2 as printl, indentXml

from Tools.Directories import resolveFilename, SCOPE_PLUGINS

# ServerSettingsData, getInstalledSkins and ServerSettings all live in
# __init__.py, and __init__.py imports THIS module before defining any of
# them (SettingsStorage is one of the first things it pulls in). Importing
# them here at module level is therefore a circular import that fails with
# "cannot import name ... from partially initialized module": at the time
# this file executes, __init__.py has not run far enough to have created
# them yet.
#
# ServerSettingsData and DP_MediaLibrary are only ever used in annotations,
# which "from __future__ import annotations" turns into unevaluated strings,
# so they do not need to be importable at runtime at all; TYPE_CHECKING keeps
# them available to type checkers without executing the import.
#
# getInstalledSkins and ServerSettings are genuinely used at runtime, so each
# is imported locally, right where it is used: by then the package has
# finished loading and the names exist.
if TYPE_CHECKING:
	from . import ServerSettingsData, ServerSettings
	from .DP_MediaLibrary import DP_MediaLibrary

PATH = "playerTempPath"
defaultPluginFolderPath = resolveFilename(SCOPE_PLUGINS, "Extensions/DreamPlex/")
defaultSkinsFolderPath = resolveFilename(SCOPE_PLUGINS, "Extensions/DreamPlex/skins/")
defaultLogFolderPath = "/tmp/"
defaultCacheFolderPath = "/hdd/dreamplex/cache/"
defaultMediaFolderPath = "/hdd/dreamplex/media/"
defaultPlayerTempPath = "/hdd/dreamplex/"
defaultConfigFolderPath = "/hdd/dreamplex/config/"

SERVER_SETTINGS_ELEMENT_NAME = "server-settings"
SERVER_SETTINGS_TYPE_ATTRIBUTE_NAME = "server-type"

#===============================================================================
# import cProfile
#===============================================================================
try:
# Python 2.5
	import xml.etree.cElementTree as etree
except ImportError:
	try:
		# Python 2.5
		import xml.etree.ElementTree as etree
	except ImportError:
		etree = None
		raise Exception

T = TypeVar('T')
C = TypeVar('C', bound=Union[ConfigElement, ConfigSubsection, None])

# Capability constants for AbstractServerSettings.getUserSwitchMode() - what
# DP_ServerMenu.onKeyGreen() reads instead of checking getType() against a
# hardcoded server-type string to decide which "switch user" UI flow to open.
# Same pattern as DP_MediaLibrary.RATING_KIND_*.
USER_SWITCH_NONE = "none"
USER_SWITCH_SHARED_HOME = "shared_home"        # Plex: home users via a shared plex.tv account
USER_SWITCH_LOCAL_PROFILES = "local_profiles"  # Jellyfin: server-local, optionally PIN-protected profiles


class AuthorizationMode(Enum):
	LOCAL = 1
	REMOTE = 2

class AuthorizationResult(Enum):
	PRINCIPAL = "principal"
	CREDENTIALS = "credentials"
	ID = "id"
	ERROR = "error"

class AbstractSettings(ABC, Generic[T]):
	def __init__(self, owner: 'SettingsStorage', parent: Element = None):
		super().__init__()
		self._settings = owner
		self._parent = parent

	@abstractmethod
	def _writeValue(self, value: T) -> None:
		pass

	@abstractmethod
	def _readValue(self) -> T:
		pass


class AbstractMappingSettings(AbstractSettings[T], ABC):
	def __init__(self, owner: 'SettingsStorage', parent: Element = None):
		super().__init__(owner, parent)

		self._id = BaseSettings[str, ConfigText]("id", ConfigText(), owner, parent)
		self._remotePath = BaseSettings[str, ConfigDirectory]("remotePath", ConfigDirectory(), owner, parent)
		self._localPath = BaseSettings[str, ConfigDirectory]("localPath", ConfigDirectory(), owner, parent)

	@property
	def id(self) -> 'BaseSettings[str, ConfigText]':
		return self._id

	@property
	def remotePath(self) -> 'BaseSettings[str, ConfigDirectory]':
		return self._remotePath

	@property
	def localPath(self) -> 'BaseSettings[str, ConfigDirectory]':
		return self._localPath

class AbstractUserSettings(AbstractSettings[T], ABC):
	def __init__(self, owner: 'SettingsStorage', parent: Element = None):
		super().__init__(owner, parent)

		self._id = BaseSettings[str, ConfigText]("id", ConfigText(), owner, parent)
		self._username = BaseSettings[str, ConfigText]("username", ConfigText(), owner, parent)
		self._pin = BaseSettings[str, ConfigText]("pin", ConfigPIN(0000), owner, parent)
		self._token = BaseSettings[str, ConfigText]("token", ConfigPassword(), owner, parent)

	@property
	def id(self) -> 'BaseSettings[str, ConfigText]':
		return self._id

	@property
	def username(self) -> 'BaseSettings[str, ConfigText]':
		return self._username

	@property
	def pin(self) -> 'BaseSettings[str, ConfigText]':
		return self._pin

	@property
	def token(self) -> 'BaseSettings[str, ConfigText]':
		return self._token

class AbstractServerSettings(AbstractSettings[T]):
	def __init__(self, owner: 'SettingsStorage', parent: Element = None):
		super().__init__(owner, parent)
		self._mappings: list[AbstractMappingSettings[T]] = []
		self._users: list[AbstractUserSettings[T]] = []

		# Wake on Lan - identical fields/behavior for every backend (sending
		# a magic packet has nothing backend-specific about it), so they live
		# here rather than being redeclared per subclass. This also means a
		# future backend (e.g. Emby) gets a working wakeOnLanAvailable() for
		# free just by extending this class, instead of silently crashing
		# with an AttributeError the first time something calls self.wol()
		# and that backend forgot to declare it.
		self._wol = BaseSettings[bool, ConfigYesNo]("wol", ConfigYesNo(), owner, parent)
		self._wol_mac = BaseSettings[str, ConfigText]("wol_mac", ConfigText(default="00AA00BB00CC", visible_width=12,
																 fixed_size=False), owner, parent)
		self._wol_delay = BaseSettings[int, ConfigInteger]("wol_delay", ConfigInteger(default=60, limits=(1, 180)), owner, parent)

	def listMappings(self) -> list[AbstractMappingSettings[T]]:
		return self._mappings

	def listUsers(self) -> list[AbstractUserSettings[T]]:
		return self._users

	def saveChanges(self) -> None:
		self._settings.writeToFile()

	def wol(self) -> 'BaseSettings[bool, ConfigYesNo]':
		return self._wol

	def wol_mac(self) -> 'BaseSettings[str, ConfigText]':
		return self._wol_mac

	def wol_delay(self) -> 'BaseSettings[int, ConfigInteger]':
		return self._wol_delay

	def wakeOnLanAvailable(self) -> bool:
		"""True if this server is configured for Wake on Lan AND reached by
		direct IP (connectionType "0") - a magic packet is a local-subnet UDP
		broadcast, so it is only meaningful when the configured address is
		presumed to be on the same LAN as this box, not a DNS name or a cloud
		relay (Plex's connectionType "2"). connectionType() itself is still
		duck-typed (declared concretely by each backend, not on this base) -
		a pre-existing gap this method inherits rather than introduces."""
		return bool(self._wol.getValue()) and str(self.connectionType().getValue()) == "0"

	def _appendWakeOnLanConfigList(self, config: list, separator: str) -> None:
		"""Shared UI section for getConfigList() - append once from each
		backend's own implementation instead of repeating these three lines
		per backend."""
		# Deferred import: this module is imported by __init__.py (line 39)
		# before __init__.py defines _() (line 46) - a module-level "from .
		# import _" here would be a circular import failing at load time.
		from . import _
		config.append(getConfigListEntry(_("Wake On Lan Settings ") + separator, self._settings.about.getConfigElement(), _(" ")))
		config.append(getConfigListEntry(_(" > Use Wake on Lan (WoL)"), self._wol.getConfigElement(), _(" ")))
		if self._wol.getValue():
			config.append(getConfigListEntry(_(" >> Mac address (Size: 12 alphanumeric no seperator) only for WoL"), self._wol_mac.getConfigElement(), _(" ")))
			config.append(getConfigListEntry(_(" >> Wait for server delay (max 180 seconds) only for WoL"), self._wol_delay.getConfigElement(), _(" ")))

	@abstractmethod
	def connectionType(self) -> 'BaseSettings[str, ConfigSelection]':
		"""Choices differ per backend (Plex adds a plex.tv cloud-relay option
		Jellyfin has no equivalent for), so this stays declared-not-shared -
		unlike wol()/wol_mac()/wol_delay() above, which are identical for
		every backend and so are implemented once, concretely, on this base
		class instead of being declared abstract here."""
		pass

	@abstractmethod
	def ip(self) -> 'BaseSettings[str, ConfigIP]':
		pass

	@abstractmethod
	def dns(self) -> 'BaseSettings[str, ConfigText]':
		pass

	@abstractmethod
	def port(self) -> 'BaseSettings[int, ConfigInteger]':
		pass

	@abstractmethod
	def isReachable(self) -> bool:
		"""True if this server can be reached right now, tested however this
		backend's own connectionType() values call for - e.g. a direct IP/
		port socket probe, a DNS-resolved host check, or (Plex only) simply
		trusting a cloud-relay connection is up. DP_MainMenu.checkServerState()
		calls this instead of ever inspecting connectionType() itself, so no
		caller needs to know what any of a backend's own connectionType
		values actually mean."""
		pass

	@abstractmethod
	def getIndex(self) -> int | None:
		pass

	@abstractmethod
	def getName(self) -> str | None:
		pass

	@abstractmethod
	def getType(self) -> str:
		pass

	@abstractmethod
	def isActive(self) -> bool:
		pass

	@abstractmethod
	def isAutostart(self) -> bool:
		pass

	@abstractmethod
	def toEntryServer(self) -> EntryServer | None:
		pass

	@abstractmethod
	def requireAuthentication(self) -> bool:
		pass

	@abstractmethod
	def pinRequired(self) -> bool:
		pass

	@abstractmethod
	def checkPin(self, pin: str)-> bool:
		pass

	@abstractmethod
	def supportServerMapping(self) -> bool:
		pass

	@abstractmethod
	def listSupportedServerMappings(self, session) -> list[str] | None:
		pass

	@abstractmethod
	def supportUsers(self) -> bool:
		pass

	@abstractmethod
	def registerServer(self, session) -> bool:
		pass

	@abstractmethod
	def buildAuthorization(self, session, mode: AuthorizationMode) -> tuple[bool, dict[AuthorizationResult, str]]:
		pass

	@abstractmethod
	def authenticateUser(self, session, principal: str, credential: str) -> tuple[bool, dict[AuthorizationResult, str]]:
		pass

	@abstractmethod
	def setupServer(self, config: list[ConfigElement]) -> dict[str, Any]:
		pass

	@abstractmethod
	def getUserSwitchMode(self) -> str:
		"""One of the USER_SWITCH_* constants above - which "switch user" UI
		flow DP_ServerMenu.onKeyGreen() should open for this server, decided
		without ever comparing getType() against a hardcoded string."""
		pass

	@abstractmethod
	def getCurrentUserDisplayName(self) -> str | None:
		"""Name shown in DP_ServerMenu's "Current User:" field - whatever
		this backend's own notion of "currently active user" is (Plex: the
		active home user, falling back to the plex.tv account; Jellyfin: the
		locally switched-to user)."""
		pass

	@abstractmethod
	def getCurrentUserAccessToken(self) -> str | None:
		"""Access token for the current user (see getCurrentUserDisplayName()
		above), or None if there isn't one yet - DP_ServerMenu applies it via
		DP_MediaLibrary.setAccessTokenHeader() when present."""
		pass

	@abstractmethod
	def getCloneExcludeFields(self) -> set[str]:
		"""Field attribute names (e.g. "_myplexToken") that a "clone this
		server for another user" action must NOT carry over - this backend's
		own identity/authentication material. Everything else on the
		instance is copied as-is by DP_Server._copyServerFields()."""
		pass

class AbstractServerSettingsFactory(ABC, Generic[T]):
	def __init__(self):
		pass

	@abstractmethod
	def createServerSettings(self, owner: "SettingsStorage", parent: Element = None) -> AbstractServerSettings[T]:
		pass

	@abstractmethod
	def createEmptyServerSettings(self, owner: "SettingsStorage", data: DiscoveredServer) -> AbstractServerSettings[T]:
		pass

	@abstractmethod
	def createNewMapping(self, server: 'AbstractServerSettings[T]', idMapping: str, remotePath: str, localPath: str) -> AbstractMappingSettings[T]:
		pass

	@abstractmethod
	def createNewUser(self, server: 'AbstractServerSettings[T]', idUser: str, username: str, pin: str, token: str) -> AbstractUserSettings[T]:
		pass

	@abstractmethod
	def createMediaLibrary(self, session, server: AbstractServerSettings[T]) -> DP_MediaLibrary:
		pass

	@abstractmethod
	def createHeader(self, g_sessionID, asDict=True):
		pass

	@abstractmethod
	def getServerHeaders(self):
		pass

	@staticmethod
	def createAutoMediaLibrary(self, session, server: AbstractServerSettings[T]) -> DP_MediaLibrary:
		from . import ServerSettings  # see the note on the TYPE_CHECKING import above
		sdata: ServerSettingsData = ServerSettings[self.g_serverConfig.getType()]
		mediaLibraryInstance: DP_MediaLibrary = sdata.factoryClass().createMediaLibrary(session, server)
		return mediaLibraryInstance

class BaseSettings(AbstractSettings[T], Generic[T, C]):
	_delegate: C

	def __init__(self, name: str, delegate: C, owner: "SettingsStorage", parent: Element = None):
		super().__init__(owner, parent)
		self._name = name
		# "_delegate: C" above is only an annotation and does not create the
		# attribute: setConfigElement inspects it, so it has to exist first.
		self._delegate = None
		self.setConfigElement(delegate)

	def setValue(self, value: T):
		if self._delegate is not None:
			self._delegate.value = value
		self._writeValue(value)

	def getValue(self) -> T:
		return self._delegate.getValue() if self._delegate is not None else self._readValue()

	def getConfigElement(self) -> C:
		return self._delegate

	def setConfigElement(self, value: C) -> None:
		if self._delegate is not None:
			self._delegate.removeNotifier(self.__notifier)

		self._delegate = value
		if value is not None:
			self._delegate.addNotifier(self.__notifier, initial_call=False, immediate_feedback=True)

			# Apply what the document holds. Assigning only to saved_value is
			# not enough: getValue() reads .value, so the stored setting would
			# never reach the element and every value would stay at its
			# default. saved_value is kept in sync so that the enigma2
			# save/cancel logic still sees the persisted value.
			stored = self._readValue()
			if stored is not None:
				try:
					self._delegate.value = stored
					self._delegate.saved_value = self._delegate.tostring(stored)
				except Exception as ex:
					printl("cannot apply stored value for " + str(self._name) + ": " + str(ex), "BaseSettings", "W")

	def name(self) -> str:
		return self._name

	def __notifier(self, configElement=None):
		# keyLeft/keyRight and the ChoiceBox-driven fields in ConfigListScreen
		# change self._delegate.value directly, bypassing setValue() below -
		# without this, the in-memory XML element never picks up the new
		# value, so saveNow()'s writeToFile() persists nothing a user typed
		# or selected, and only whatever was already on disk (usually just
		# the defaults) survives a restart.
		self._writeValue(self._delegate.getValue())

	def _writeValue(self, value: T) -> None:
		parent = self._parent
		if parent is None:
			parent = self._settings.root
		elem:Element = parent.find(self._name)

		v: T =  self._delegate.tostring(value) if self._delegate is not None else str(value)

		if elem is None:
			# etree.Element(tag, text=...) would store the value as an
			# ATTRIBUTE called "text", while _readValue reads elem.text: the
			# value has to be assigned to the element after creating it, or
			# every newly created setting is silently lost on reload.
			elem = etree.SubElement(parent, self._name)

		elem.text = v

	def _readValue(self) -> T:
		parent = self._parent
		if self._parent is None:
			parent = self._settings.root
		elem = parent.find(self._name)
		strValue: str = elem.text if elem is not None and elem.text is not None else None
		return self._delegate.fromstring(strValue) if self._delegate is not None and strValue is not None else strValue

def compareServers(s: AbstractServerSettings):
	idServer = s.getIndex()
	return idServer

class SettingsStorage(object):
	def __init__(self, location: str):
		self.location = location
		self._serverConfigs: list[AbstractServerSettings] = []

		self._readFromFile()

		self._debugMode = BaseSettings[bool, ConfigYesNo]("debugMode", ConfigYesNo(), self)
		self._writeDebugFile = BaseSettings[bool, ConfigYesNo]("writeDebugFile", ConfigYesNo(), self)
		self._playerTempPath = BaseSettings[str, ConfigDirectory]("playerTempPath", ConfigDirectory(default=defaultPlayerTempPath, visible_width=50), self)
		self._cacheFolderPath = BaseSettings[str, ConfigDirectory]("cacheFolderPath", ConfigDirectory(default=defaultCacheFolderPath, visible_width=50), self)
		self._logFolderPath = BaseSettings[str, ConfigDirectory]("logFolderPath", ConfigDirectory(default=defaultLogFolderPath, visible_width=50), self)
		self._mediaFolderPath = BaseSettings[str, ConfigDirectory]("mediaFolderPath", ConfigDirectory(default=defaultMediaFolderPath, visible_width=50), self)
		self._configFolderPath = BaseSettings[str, ConfigDirectory]("configFolderPath", ConfigDirectory(default=defaultConfigFolderPath, visible_width=50), self)
		self._homeUsersFolderPath = BaseSettings[str, ConfigDirectory]("homeUsersFolderPath", ConfigDirectory(default=defaultPluginFolderPath, visible_width=50), self)
		self._boxName = BaseSettings[str, ConfigText]("boxName", ConfigText(default="DreamPlex", visible_width=50, fixed_size=False), self)

		self._about = BaseSettings[str, ConfigSelection]("about", ConfigSelection(default="1", choices=[("1", " ")]) , self) # need this for seperator in settings
		self._showInMainMenu = BaseSettings[bool, ConfigYesNo]("showInMainMenu", ConfigYesNo(default=True), self)
		self._showFilter = BaseSettings[bool, ConfigYesNo]("showFilter", ConfigYesNo(default=True), self)
		self._autoLanguage = BaseSettings[bool, ConfigYesNo]("autoLanguage", ConfigYesNo(), self)
		self._playTheme = BaseSettings[bool, ConfigYesNo]("playTheme", ConfigYesNo(), self)
		self._showUnSeenCounts = BaseSettings[bool, ConfigYesNo]("showUnSeenCounts", ConfigYesNo(), self)
		self._fastScroll = BaseSettings[bool, ConfigYesNo]("fastScroll", ConfigYesNo(), self)
		self._liveTvInViews = BaseSettings[bool, ConfigYesNo]("liveTvInViews", ConfigYesNo(), self)
		self._startWithFilterMode = BaseSettings[bool, ConfigYesNo]("startWithFilterMode", ConfigYesNo(), self)
		self._summerizeSections = BaseSettings[bool, ConfigYesNo]("summerizeSections", ConfigYesNo(default=True), self)
		self._summerizeServers = BaseSettings[bool, ConfigYesNo]("summerizeServers", ConfigYesNo(default=True), self)
		self._stopLiveTvOnStartup = BaseSettings[bool, ConfigYesNo]("stopLiveTvOnStartup", ConfigYesNo(), self)
		self._useCache = BaseSettings[bool, ConfigYesNo]("useCache", ConfigYesNo(default=True), self)
		self._usePicCache = BaseSettings[bool, ConfigYesNo]("usePicCache", ConfigYesNo(default=True), self)
		self._useBackdropVideos = BaseSettings[bool, ConfigYesNo]("useBackdropVideos", ConfigYesNo(), self)
		self._showDetailsInList = BaseSettings[bool, ConfigYesNo]("showDetailsInList", ConfigYesNo(), self)
		self._showDetailsInListDetailType = BaseSettings[str, ConfigSelection]("showDetailsInListDetailType", ConfigSelection(default="1", choices=[("1", "user"), ("2", "server")]) , self)
		self._lcd4linux = BaseSettings[bool, ConfigYesNo]("lcd4linux", ConfigYesNo(), self)
		self._exitFunction = BaseSettings[str, ConfigSelection]("exitFunction", ConfigSelection(default="0", choices=[("0", "Nothing"), ("1", "stop playback, return to library"), ("2", "search library while playing")]) , self)
		self._pluginFolderPath = BaseSettings[str, ConfigDirectory]("pluginFolderPath", ConfigDirectory(default=defaultPluginFolderPath), self)
		self._skinFolderPath = BaseSettings[str, ConfigDirectory]("skinFolderPath", ConfigDirectory(default=defaultSkinsFolderPath), self)

		from . import getInstalledSkins  # see the note on the TYPE_CHECKING import above
		# self._skinFolderPath (not Singleton().getSettingsInstance()) - this
		# SettingsStorage instance is not registered into the Singleton until
		# after __init__ returns, see initSettingsStorage() in __init__.py.
		myDefaultSkin, mySkins = getInstalledSkins(self._skinFolderPath.getValue())

		self._skinName = BaseSettings[str, ConfigText]("skinName", ConfigSelection(default=myDefaultSkin, choices=mySkins), self)
		self._remoteAgent = BaseSettings[bool, ConfigYesNo]("remoteAgent", ConfigYesNo(), self)
		self._remotePort = BaseSettings[int, ConfigInteger]("remotePort", ConfigInteger(default=32400, limits=(1, 65555)), self)
		self._seekTime = BaseSettings[int, ConfigInteger]("seekTime", ConfigInteger(default=5, limits=(1, 30)), self)

		# Prompt offering to move on to the next episode towards the end of an
		# episode. The threshold is how many seconds before the end it shows
		# up, the countdown how many seconds to wait before moving on by
		# ourselves.
		self._showNextEpisode = BaseSettings[bool, ConfigYesNo]("showNextEpisode", ConfigYesNo(default=True), self)
		self._nextEpisodeThreshold = BaseSettings[int, ConfigInteger]("nextEpisodeThreshold", ConfigInteger(default=30, limits=(5, 300)), self)
		self._nextEpisodeCountdown = BaseSettings[int, ConfigInteger]("nextEpisodeCountdown", ConfigInteger(default=15, limits=(3, 120)), self)

		# Same prompt/timing as above, but for the "you might also like"
		# suggestion offered near the end of a standalone movie (no next
		# playlist entry to fall back to there, unlike a show) - off by
		# default: unlike a real next episode, this is not something the
		# user already committed to watching, so it should not start
		# playing itself unless asked to.
		self._similarSuggestionAutoplay = BaseSettings[bool, ConfigYesNo]("similarSuggestionAutoplay", ConfigYesNo(default=False), self)

		# Carousel skin's rotating "hero" banner on the main menu (see
		# DP_MediaLibrary.getHeroSuggestions()). 0 = rotation off (still
		# shows the first suggestion, just never changes it on its own -
		# OK still plays whatever is showing).
		self._heroRotationInterval = BaseSettings[int, ConfigInteger]("heroRotationInterval", ConfigInteger(default=8, limits=(0, 120)), self)
		# How many full rotations through the current suggestion list
		# before asking the backend for a fresh one - keeps the door open
		# for a getHeroSuggestions() that returns something different each
		# time (e.g. excluding what was already shown) without the timer
		# logic itself needing to know or care.
		self._heroRefetchAfterLoops = BaseSettings[int, ConfigInteger]("heroRefetchAfterLoops", ConfigInteger(default=3, limits=(1, 50)), self)
		# Upper bound passed as getHeroSuggestions(limit=...) - the actual
		# count is still whatever the server has to offer (On Deck/Resume
		# and Recently Added/Latest can both come back shorter than this),
		# this just caps how many it is ever asked for.
		self._heroMaxItems = BaseSettings[int, ConfigInteger]("heroMaxItems", ConfigInteger(default=6, limits=(1, 30)), self)

		self._defaultMovieView = BaseSettings[str, ConfigSelection]("defaultMovieView", None, self)
		self._defaultShowView = BaseSettings[str, ConfigSelection]("defaultShowView", None, self)
		self._defaultMusicView = BaseSettings[str, ConfigSelection]("defaultMusicView", None, self)

		# Not shown in the settings UI (no cfglist entry) - just remembers
		# which version last ran, so Autostart can offer a GUI restart after
		# an install/update instead of leaving stale code loaded until the
		# user restarts enigma2 themselves.
		self._lastSeenVersion = BaseSettings[str, ConfigText]("lastSeenVersion", ConfigText(default=""), self)

		self._uniqueIds = itertools.count()

		pass

	@property
	def debugMode(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._debugMode

	@property
	def cacheFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._cacheFolderPath

	@property
	def writeDebugFile(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._writeDebugFile

	@property
	def logFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._logFolderPath

	@property
	def playerTempPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._playerTempPath

	@property
	def mediaFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._mediaFolderPath

	@property
	def configFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._configFolderPath

	@property
	def homeUsersFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._homeUsersFolderPath

	@property
	def boxName(self) -> BaseSettings[str, ConfigText]:
		return self._boxName

	@property
	def about(self) -> BaseSettings[str, ConfigSelection]:
		return self._about

	@property
	def showInMainMenu(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._showInMainMenu


	@property
	def showFilter(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._showFilter


	@property
	def autoLanguage(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._autoLanguage


	@property
	def playTheme(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._playTheme


	@property
	def showUnSeenCounts(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._showUnSeenCounts


	@property
	def fastScroll(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._fastScroll


	@property
	def liveTvInViews(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._liveTvInViews


	@property
	def startWithFilterMode(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._startWithFilterMode


	@property
	def summerizeSections(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._summerizeSections


	@property
	def summerizeServers(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._summerizeServers


	@property
	def stopLiveTvOnStartup(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._stopLiveTvOnStartup


	@property
	def useCache(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._useCache


	@property
	def usePicCache(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._usePicCache


	@property
	def useBackdropVideos(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._useBackdropVideos


	@property
	def showDetailsInList(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._showDetailsInList


	@property
	def showDetailsInListDetailType(self) -> BaseSettings[str, ConfigSelection]:
		return self._showDetailsInListDetailType


	@property
	def lcd4linux(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._lcd4linux


	@property
	def exitFunction(self) -> BaseSettings[str, ConfigSelection]:
		return self._exitFunction


	@property
	def pluginFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._pluginFolderPath


	@property
	def skinFolderPath(self) -> BaseSettings[str, ConfigDirectory]:
		return self._skinFolderPath

	@property
	def skinName(self) -> BaseSettings[str, ConfigText]:
		return self._skinName

	@property
	def remoteAgent(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._remoteAgent


	@property
	def remotePort(self) -> BaseSettings[int, ConfigInteger]:
		return self._remotePort

	@property
	def lastSeenVersion(self) -> BaseSettings[str, ConfigText]:
		return self._lastSeenVersion


	@property
	def seekTime(self) -> BaseSettings[int, ConfigInteger]:
		return self._seekTime

	@property
	def showNextEpisode(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._showNextEpisode

	@property
	def nextEpisodeThreshold(self) -> BaseSettings[int, ConfigInteger]:
		return self._nextEpisodeThreshold

	@property
	def nextEpisodeCountdown(self) -> BaseSettings[int, ConfigInteger]:
		return self._nextEpisodeCountdown

	@property
	def similarSuggestionAutoplay(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._similarSuggestionAutoplay

	@property
	def heroRotationInterval(self) -> BaseSettings[int, ConfigInteger]:
		return self._heroRotationInterval

	@property
	def heroRefetchAfterLoops(self) -> BaseSettings[int, ConfigInteger]:
		return self._heroRefetchAfterLoops

	@property
	def heroMaxItems(self) -> BaseSettings[int, ConfigInteger]:
		return self._heroMaxItems

	@property
	def defaultMovieView(self) -> BaseSettings[str, ConfigSelection]:
		return self._defaultMovieView

	@property
	def defaultShowView(self) -> BaseSettings[str, ConfigSelection]:
		return self._defaultShowView

	@property
	def defaultMusicView(self) -> BaseSettings[str, ConfigSelection]:
		return self._defaultMusicView

	@property
	def entriesCount(self) -> int:
		return len(self._serverConfigs)

	@property
	def serverConfigs(self) -> list[AbstractServerSettings]:
		return self._serverConfigs

	def writeToFile(self) -> None:
		with self.lock:
			indentXml(self.root)
			self.tree.write(self.location)

	def _readFromFile(self) -> None:
		from . import ServerSettings  # see the note on the TYPE_CHECKING import above
		self.tree = etree.parse(self.location)
		self.root = self.tree.getroot()
		self.lock = threading.Lock()

		servers: list[Element] = self.root.findall("server-settings")
		nextId: int = -1
		for server in servers:
			stype: str | None = server.get("server-type")
			ttype = Type[AbstractServerSettingsFactory]

			if stype:
				ttype = ServerSettings[stype].factoryClass

			if ttype:
				s: AbstractServerSettingsFactory = ttype()
				ns: AbstractServerSettings = s.createServerSettings(self, server)
				nextId = ns.getIndex() if ns.getIndex() > nextId else nextId
				self._serverConfigs.append(ns)

		self._uniqueIds = itertools.count(nextId + 1)
		self._serverConfigs.sort(key=compareServers)

	def getUniqueId(self) -> int:
		return next(self._uniqueIds)

	def registerNewServer(self, server: AbstractServerSettings) -> None:
		"""Wire a freshly created server into the document and the live list.

		createServerSettings() / createEmptyServerSettings() build a server
		object with its own standalone <server-settings> Element when called
		without a parent, but never attach that element to self.root, and
		never add the object to self._serverConfigs. Without this, the new
		server's fields do get written into its Element as they are set (each
		BaseSettings writes into server._parent on setValue), but that Element
		is never reachable from self.root: writeToFile() only serializes what
		hangs off the root, so the whole thing is silently dropped, and the
		server never survives a reload. DP_Server.keyCancel() already assumes
		this registration happened - it removes the entry from serverConfigs
		on cancel - so this completes that half of the lifecycle.
		"""
		if server._parent is not None and server._parent not in list(self.root):
			self.root.append(server._parent)
		if server not in self._serverConfigs:
			self._serverConfigs.append(server)
			self._serverConfigs.sort(key=compareServers)