from __future__ import annotations
from typing import Any
from xml.etree.ElementTree import Element

from .. import AbstractServerSettingsFactory, Singleton
from ..__common__ import EntryServer, DiscoveredServer, printl2 as printl, printl2, getBoxInformation, getVersion, \
	getUUID, testMediaServerConnectivity, testInetConnectivity
from .. import _

from Components.config import ConfigInteger, ConfigYesNo, ConfigText, ConfigSelection, ConfigIP, ConfigPIN, \
	getConfigListEntry, ConfigElement
from ..DP_SettingsStorage import SettingsStorage, T, BaseSettings, AbstractServerSettings, SERVER_SETTINGS_ELEMENT_NAME, \
	SERVER_SETTINGS_TYPE_ATTRIBUTE_NAME, AuthorizationMode, AuthorizationResult, AbstractMappingSettings, \
	AbstractUserSettings, USER_SWITCH_SHARED_HOME

_CONNECTION_TYPE_IP = "0"
_CONNECTION_TYPE_DNS = "1"
_CONNECTION_TYPE_PLEX_TV = "2"


class PlexSettings(AbstractServerSettings["PlexSettings"]):
	SETTINGS_NAME: str = "PlexServer"

	def __init__(self, owner: SettingsStorage, parent: Element = None):
		if not parent:
			parent = Element(SERVER_SETTINGS_ELEMENT_NAME, {SERVER_SETTINGS_TYPE_ATTRIBUTE_NAME: self.SETTINGS_NAME})
		super().__init__(owner, parent)

		default_name = "PlexServer"
		default_ip = [192, 168, 0, 1]
		default_port = 32400

		# SERVER SETTINGS
		self._id = BaseSettings[int, ConfigInteger]("id", ConfigInteger(default=-1), owner, parent)
		self._state = BaseSettings[bool, ConfigYesNo]("state", ConfigYesNo(default=True), owner, parent)
		self._autostart = BaseSettings[bool, ConfigYesNo]("autostart", ConfigYesNo(), owner, parent)
		self._name = BaseSettings[str, ConfigText]("name", ConfigText(default=default_name, visible_width=50, fixed_size=False), owner, parent)
		self._connectionType = BaseSettings[str, ConfigSelection]("connectionType", ConfigSelection(default="0",
																									choices=[(_CONNECTION_TYPE_IP, _("IP")),
																											 (_CONNECTION_TYPE_DNS, _("DNS")),
																											 (_CONNECTION_TYPE_PLEX_TV, _("plex.tv"))]), owner, parent)
		self._ip = BaseSettings[str, ConfigIP]("ip", ConfigIP(default=default_ip), owner, parent)
		self._dns = BaseSettings[str, ConfigText]("dns", ConfigText(default="my.dns.url", visible_width=50, fixed_size=False), owner, parent)
		self._port = BaseSettings[int, ConfigInteger]("port", ConfigInteger(default=default_port, limits=(1, 65555)), owner, parent)
		self._playbackType = BaseSettings[str, ConfigSelection]("playbackType",
																ConfigSelection(default="0", choices=[("0", _("Streamed")),
																										 ("1", _("Transcoded")),
																										 ("2", _("Direct Local"))]), owner, parent)
		self._localAuth = BaseSettings[bool, ConfigYesNo]("localAuth", ConfigYesNo(), owner, parent)
		self._machineIdentifier = BaseSettings[str, ConfigText]("machineIdentifier",
																ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._loadExtraData = BaseSettings[str, ConfigSelection]("loadExtraData", ConfigSelection(default="0", choices=[("0", "None"), ("1", "Plex Pass"),("2", "YTTrailer")]), owner, parent)

		self._srtRenamingForDirectLocal = BaseSettings[bool, ConfigYesNo]("srtRenamingForDirectLocal", ConfigYesNo(), owner, parent)
		self._subtitlesLanguage = BaseSettings[str, ConfigText]("subtitlesLanguage", ConfigText(default="de", visible_width=10, fixed_size=False), owner, parent)
		self._useForcedSubtitles = BaseSettings[bool, ConfigYesNo]("useForcedSubtitles", ConfigYesNo(default=True), owner, parent)

		printl("=== SERVER SETTINGS ===", "PlexSettings::__init__", "D")
		printl("Server Settings: ", "PlexSettings::__init__", "D")
		printl("id: " + str(self._id.getValue()), "PlexSettings::__init__", "D")
		printl("state: " + str(self._state.getValue()), "PlexSettings::__init__", "D")
		printl("autostart: " + str(self._autostart.getValue()),"PlexSettings::__init__", "D")
		printl("name: " + str(self._name.getValue()), "PlexSettings::__init__", "D")
		printl("connectionType: " + str(self._connectionType.getValue()), "PlexSettings::__init__", "D")
		printl("ip: " + str(self._ip.getValue()), "PlexSettings::__init__", "D")
		printl("dns: " + str(self._dns.getValue()), "PlexSettings::__init__", "D")
		printl("port: " + str(self._port.getValue()), "PlexSettings::__init__", "D")
		printl("playbackType: " + str(self._playbackType.getValue()), "PlexSettings::__init__", "D")

		# plex.tv
		self._myplexUrl = BaseSettings[str, ConfigText]("myplexUrl", ConfigText(default="plex.tv", visible_width=50, fixed_size=False), owner, parent)
		self._myplexUsername = BaseSettings[str, ConfigText]("myplexUsername", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexId = BaseSettings[int, ConfigInteger]("myplexId", ConfigInteger(default=0, limits=(1, 999999999999)), owner, parent)
		self._myplexPassword = BaseSettings[str, ConfigText]("myplexPassword", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexPinProtect = BaseSettings[bool, ConfigYesNo]("myplexPinProtect", ConfigYesNo(), owner, parent)
		self._myplexPin = BaseSettings[str, ConfigPIN]("myplexPin", ConfigPIN(default=0000), owner, parent)
		self._myplexToken = BaseSettings[str, ConfigText]("myplexToken", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexLocalToken = BaseSettings[str, ConfigText]("myplexLocalToken", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexTokenUsername = BaseSettings[str, ConfigText]("myplexTokenUsername", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexHomeUsers = BaseSettings[bool, ConfigYesNo]("myplexHomeUsers", ConfigYesNo(), owner, parent)
		self._protectSettings = BaseSettings[bool, ConfigYesNo]("protectSettings", ConfigYesNo(), owner, parent)
		self._settingsPin = BaseSettings[str, ConfigPIN]("settingsPin", ConfigPIN(default=0000), owner, parent)
		self._myplexCurrentHomeUser = BaseSettings[str, ConfigText]("myplexCurrentHomeUser", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._myplexCurrentHomeUserPin = BaseSettings[str, ConfigText]("myplexCurrentHomeUserPin", ConfigText(visible_width=4), owner, parent)
		self._myplexCurrentHomeUserAccessToken = BaseSettings[str, ConfigText]("myplexCurrentHomeUserAccessToken", ConfigText(visible_width=4), owner, parent)
		self._myplexCurrentHomeUserId = BaseSettings[int, ConfigInteger]("myplexCurrentHomeUserId", ConfigInteger(default=0, limits=(1, 999999999999)), owner, parent)

		printl("=== plex.tv ===", "PlexSettings::__init__", "D")
		printl("plex.tvUrl: " + str(self._myplexUrl.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvUsername: " + str(self._myplexUsername.getValue()), "PlexSettings::__init__", "D", True, 8)
		printl("plex.tvId: " + str(self._myplexId.getValue()), "PlexSettings::__init__", "D", True, 8)
		printl("plex.tvPassword: " + str(self._myplexPassword.getValue()), "PlexSettings::__init__", "D", True, 6)
		printl("plex.tvPinProtect: " + str(self._myplexPinProtect.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvPin: " + str(self._myplexPin.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvToken: " + str(self._myplexToken.getValue()), "PlexSettings::__init__", "D", True, 8)
		printl("plex.tvTokenUsername: " + str(self._myplexTokenUsername.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvHomeUsers: " + str(self._myplexHomeUsers.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvCurrentHomeUser: " + str(self._myplexCurrentHomeUser.getValue()), "PlexSettings::__init__", "D")
		printl("plex.tvCurrentHomeUserPin: " + str(self._myplexCurrentHomeUserPin.getValue()), "PlexSettings::__init__", "D")
		printl("protectSettings: " + str(self._protectSettings.getValue()), "PlexSettings::__init__", "D")
		printl("settingsPin: " + str(self._settingsPin.getValue()), "PlexSettings::__init__", "D")

		# STREAMED
		# no options at the moment

		# TRANSCODED
		self._universalTranscoder = BaseSettings[bool, ConfigYesNo]("universalTranscoder", ConfigYesNo(default=True), owner, parent)

		# old transcoder settings
		self._quality = BaseSettings[str, ConfigSelection]("quality", ConfigSelection(default="7",
																	  choices=[("0", _("64kbps, 128p, 3fps")),
																			   ("1", _("96kbps, 128p, 12fps")),
																			   ("2", _("208kbps, 160p, 15fps")),
																			   ("3", _("320kbps, 240p")),
																			   ("4", _("720kbps, 320p")),
																			   ("5", _("1.5Mbps, 480p")),
																			   ("6", _("2Mbps, 720p")),
																			   ("7", _("3Mbps, 720p")),
																			   ("8", _("4Mbps, 720p")),
																			   ("9", _("8Mbps, 1080p")),
																			   ("10", _("10Mbps, 1080p")),
																			   ("11", _("12Mbps, 1080p")),
																			   ("12", _("20Mbps, 1080p"))]), owner, parent)
		self._segments = BaseSettings[int, ConfigInteger]("segments", ConfigInteger(default=5, limits=(1, 10)), owner, parent)

		# universal transcoder settings
		self._uniQuality = BaseSettings[str, ConfigSelection]("uniQuality", ConfigSelection(default="3",
																		 choices=[("0", _("420x240, 320kbps")),
																				  ("1", _("576x320, 720 kbps")),
																				  ("2", _("720x480, 1,5mbps")),
																				  ("3", _("1024x768, 2mbps")),
																				  ("4", _("1280x720, 3mbps")),
																				  ("5", _("1280x720, 4mbps")),
																				  ("6", _("1920x1080, 8mbps")),
																				  ("7", _("1920x1080, 10mbps")),
																				  ("8", _("1920x1080, 12mbps")),
																				  ("9", _("1920x1080, 20mbps"))]), owner, parent)

		printl("=== TRANSCODED ===", "PlexSettings::__init__", "D")
		printl("universalTranscoder: " + str(self._universalTranscoder.getValue()), "PlexSettings::__init__", "D")
		printl("quality: " + str(self._quality.getValue()), "PlexSettings::__init__", "D")
		printl("segments: " + str(self._segments.getValue()), "PlexSettings::__init__", "D")
		printl("uniQuality: " + str(self._uniQuality.getValue()), "PlexSettings::__init__", "D")

		# TRANSCODED VIA PROXY

		# DIRECT LOCAL
		printl("=== DIRECT LOCAL ===", "PlexSettings::__init__", "D")
		printl("use forced subtitles: " + str(self._useForcedSubtitles.getValue()), "PlexSettings::__init__", "D")

		# DIRECT REMOTE
		self._smbUser = ConfigText(visible_width=50, fixed_size=False)
		self._smbPassword = ConfigText(visible_width=50, fixed_size=False)
		self._nasOverrideIp = ConfigIP(default=[192, 168, 0, 1])
		self._nasRoot = ConfigText(default="/", visible_width=50, fixed_size=False)

		printl("=== DIRECT REMOTE ===", "PlexSettings::__init__", "D")
		printl("smbUser: " + str(self._smbUser.getValue()), "PlexSettings::__init__", "D", True)
		printl("smbPassword: " + str(self._smbPassword.getValue()), "PlexSettings::__init__", "D", True)
		printl("nasOverrideIp: " + str(self._nasOverrideIp.getValue()), "PlexSettings::__init__", "D")
		printl("nasRoot: " + str(self._nasRoot.getValue()), "PlexSettings::__init__", "D")

		# WOL fields/accessors are declared once on AbstractServerSettings
		# (see DP_SettingsStorage.py) - identical for every backend.

		printl("=== SYNC ===", "PlexSettings::__init__", "D")
		self._syncMovies = BaseSettings[bool, ConfigYesNo]("syncMovies", ConfigYesNo(default=True), owner, parent)
		self._syncShows = BaseSettings[bool, ConfigYesNo]("syncShows", ConfigYesNo(default=True), owner, parent)
		self._syncMusic = BaseSettings[bool, ConfigYesNo]("syncMusic", ConfigYesNo(default=True), owner, parent)

		printl("", "PlexSettings::__init__", "C")

	def id(self) -> BaseSettings[int, ConfigInteger]:
		return self._id

	def state(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._state

	def autostart(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._autostart

	def name(self) -> BaseSettings[str, ConfigText]:
		return self._name

	def connectionType(self) -> BaseSettings[str, ConfigSelection]:
		return self._connectionType

	def ip(self) -> BaseSettings[str, ConfigIP]:
		return self._ip

	def dns(self) -> BaseSettings[str, ConfigText]:
		return self._dns

	def port(self) -> BaseSettings[int, ConfigInteger]:
		return self._port

	def isReachable(self) -> bool:
		connType = str(self._connectionType.getValue())
		if connType == _CONNECTION_TYPE_IP:
			ip = "%d.%d.%d.%d" % tuple(self._ip.getValue())
			port = int(self._port.getValue())
			return testMediaServerConnectivity(ip, port)
		if connType == _CONNECTION_TYPE_PLEX_TV:
			# The cloud relay's own reachability isn't something a direct
			# socket probe can test - the closest meaningful check
			# (whether this box has an internet connection at all) is done
			# right below for the DNS case anyway, so just trust plex.tv is
			# up rather than doubling that check for no real benefit.
			return True
		return testInetConnectivity()

	def playbackType(self) -> BaseSettings[str, ConfigSelection]:
		return self._playbackType

	def localAuth(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._localAuth

	def machineIdentifier(self) -> BaseSettings[str, ConfigText]:
		return self._machineIdentifier

	def loadExtraData(self) -> BaseSettings[str, ConfigSelection]:
		return self._loadExtraData

	def srtRenamingForDirectLocal(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._srtRenamingForDirectLocal

	def subtitlesLanguage(self) -> BaseSettings[str, ConfigText]:
		return self._subtitlesLanguage

	def useForcedSubtitles(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._useForcedSubtitles

	def quality(self) -> BaseSettings[str, ConfigSelection]:
		return self._quality

	def segments(self) -> BaseSettings[int, ConfigInteger]:
		return self._segments

	def uniQuality(self) -> BaseSettings[str, ConfigSelection]:
		return self._uniQuality

	def universalTranscoder(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._universalTranscoder

	def syncMovies(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._syncMovies

	def syncShows(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._syncShows

	def syncMusic(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._syncMusic

	def myplexUrl(self) -> BaseSettings[str, ConfigText]:
		return self._myplexUrl

	def myplexUsername(self) -> BaseSettings[str, ConfigText]:
		return self._myplexUsername

	def myplexId(self) -> BaseSettings[int, ConfigInteger]:
		return self._myplexId

	def myplexPassword(self) -> BaseSettings[str, ConfigText]:
		return self._myplexPassword

	def myplexPinProtect(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._myplexPinProtect

	def myplexPin(self) -> BaseSettings[str, ConfigPIN]:
		return self._myplexPin

	def myplexToken(self) -> BaseSettings[str, ConfigText]:
		return self._myplexToken

	def myplexLocalToken(self) -> BaseSettings[str, ConfigText]:
		return self._myplexLocalToken

	def myplexTokenUsername(self) -> BaseSettings[str, ConfigText]:
		return self._myplexTokenUsername

	def myplexHomeUsers(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._myplexHomeUsers

	def protectSettings(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._protectSettings

	def settingsPin(self) -> BaseSettings[str, ConfigPIN]:
		return self._settingsPin

	def myplexCurrentHomeUser(self) -> BaseSettings[str, ConfigText]:
		return self._myplexCurrentHomeUser

	def myplexCurrentHomeUserPin(self) -> BaseSettings[str, ConfigText]:
		return self._myplexCurrentHomeUserPin

	def myplexCurrentHomeUserAccessToken(self) -> BaseSettings[str, ConfigText]:
		return self._myplexCurrentHomeUserAccessToken

	def myplexCurrentHomeUserId(self) -> BaseSettings[int, ConfigInteger]:
		return self._myplexCurrentHomeUserId

	def getIndex(self) -> int:
		return self._id.getValue() if self._id.getValue() is not None else None

	def getName(self) -> str | None:
		return self._name.getValue()

	def getType(self) -> str:
		return self.SETTINGS_NAME

	def getUserSwitchMode(self) -> str:
		return USER_SWITCH_SHARED_HOME

	def getCurrentUserDisplayName(self) -> str | None:
		currentHomeUser = self._myplexCurrentHomeUser.getValue()
		if currentHomeUser:
			return currentHomeUser
		return self._myplexTokenUsername.getValue()

	def getCurrentUserAccessToken(self) -> str | None:
		if self._myplexCurrentHomeUser.getValue():
			return self._myplexCurrentHomeUserAccessToken.getValue()
		return None

	def getCloneExcludeFields(self) -> set[str]:
		# Plex identity/session state: the myplex.tv account, its home-user
		# session, and the settings-screen PIN (a secret, not a preference -
		# the clone must not inherit a PIN it was never shown to its new
		# owner).
		return {
			"_id", "_myplexUsername", "_myplexId", "_myplexPassword", "_myplexToken", "_myplexLocalToken",
			"_myplexTokenUsername", "_myplexCurrentHomeUser", "_myplexCurrentHomeUserPin",
			"_myplexCurrentHomeUserAccessToken", "_myplexCurrentHomeUserId", "_myplexPinProtect", "_myplexPin",
			"_protectSettings", "_settingsPin",
		}

	def isActive(self) -> bool:
		return self._state.getValue()

	def isAutostart(self) -> bool:
		return self._autostart.getValue()

	def requireAuthentication(self) -> bool:
		return self._localAuth.getValue() or self._connectionType.getValue() == _CONNECTION_TYPE_PLEX_TV

	def toEntryServer(self) -> EntryServer:
		if self._connectionType.getValue() == _CONNECTION_TYPE_PLEX_TV:
			return EntryServer(name=self.getName(),
							   serverHost=self._myplexUrl.getValue(),
							   serverPort=None,
							   username=self._myplexUsername.getValue(),
							   settings=self,
							   active=str(self._state.getValue()))
		else:
			return EntryServer(name=self.getName(),
							   serverHost="%d.%d.%d.%d" % tuple(self._ip.getValue()),
							   username=None,
							   serverPort="%d" % self._port.getValue(),
							   settings=self,
							   active=str(self._state.getValue()))

	def pinRequired(self) -> bool:
		return self._protectSettings.getValue() and self._myplexPinProtect.getValue()

	def checkPin(self, pin: str) -> bool:
		return pin == self._settingsPin.getValue()

	def supportServerMapping(self) -> bool:
		return True

	def listSupportedServerMappings(self, session) -> list[str] | None:
		# imported here to avoid a circular import at module load time
		from .DP_PlexLibrary import PlexLibrary
		plexInstance = Singleton().getMediaLibrary(PlexLibrary(session, self))
		serverpaths = plexInstance.getServerSectionPaths()
		return serverpaths

	def registerServer(self, session) -> bool:
		# if self.current.machineIdentifier.value == "":

		# imported here to avoid a circular import at module load time
		from .DP_PlexLibrary import PlexLibrary
		plexInstance = Singleton().getMediaLibrary(PlexLibrary(session, self))

		machineIdentifiers = ""

		if self._connectionType.getValue() == _CONNECTION_TYPE_PLEX_TV:
			xmlResponse = plexInstance.getSharedServerForUser()
			machineIdentifier = xmlResponse.get("machineIdentifier")
			if machineIdentifier is not None:
				machineIdentifiers += machineIdentifier

			servers = xmlResponse.findall("Server")
			for server in servers:
				machineIdentifier = server.get("machineIdentifier")
				if machineIdentifier is not None:
					machineIdentifiers += ", " + machineIdentifier

		else:
			http = plexInstance.http
			url = "%s://%s:%s" % (http, str(plexInstance.g_host), str(plexInstance.serverConfig_port))
			xmlResponse = plexInstance.getXmlTreeFromUrl(url)
			machineIdentifier = xmlResponse.get("machineIdentifier")

			if machineIdentifier is not None:
				machineIdentifiers += xmlResponse.get("machineIdentifier")

		self._machineIdentifier.setValue(machineIdentifiers)
		printl("machineIdentifier: " + str(machineIdentifiers), self, "D")

		return True

	def buildAuthorization(self, session, mode: AuthorizationMode) -> tuple[bool, dict[AuthorizationResult, str]]:
		# now that we know the server we establish global plexInstance
		# imported here to avoid a circular import at module load time
		from .DP_PlexLibrary import PlexLibrary
		plexInstance = Singleton().getMediaLibrary(PlexLibrary(session, self))

		if mode == AuthorizationMode.LOCAL:
			ipInConfig = "%d.%d.%d.%d" % tuple(self.ip().getValue())
			token = plexInstance.getUserTokenForLocalServerAuthentication(ipInConfig)

			if token:
				self._myplexLocalToken.setValue(token)
				self._settings.writeToFile()
				return (True, {AuthorizationResult.PRINCIPAL: self._myplexTokenUsername.getValue(), AuthorizationResult.CREDENTIALS: token})
			else:
				response = plexInstance.getLastResponse()
				return (False, {AuthorizationResult.PRINCIPAL: self._myplexTokenUsername.getValue(), AuthorizationResult.ERROR: response})
		elif mode == AuthorizationMode.REMOTE:
			token = plexInstance.getNewMyPlexToken()

			if token:
				return (True, {AuthorizationResult.PRINCIPAL: self._myplexTokenUsername.getValue(), AuthorizationResult.CREDENTIALS: token, AuthorizationResult.ID: self._myplexId.getValue()})
			else:
				response = plexInstance.getLastResponse()
				return (False, {AuthorizationResult.PRINCIPAL: self._myplexTokenUsername.getValue(), AuthorizationResult.ERROR: response})
		else:
			return (False, {AuthorizationResult.ERROR: _("Unknown AuthorizationMode")})

	def supportUsers(self) -> bool:
		return True

	def authenticateUser(self, session, principal: str, credential: str) -> tuple[bool, dict[AuthorizationResult, str]]:
		# imported here to avoid a circular import at module load time
		from .DP_PlexLibrary import PlexLibrary
		plexInstance = Singleton().getMediaLibrary(PlexLibrary(session, self))
		xmlResponse = plexInstance.getAlternateUsers()

		authenticationToken: str | None = None
		myId: str | None = None

		if xmlResponse is not False:
			users = xmlResponse.findall('User')
			foundMatchingUser = False

			for user in users:
				entryData = (dict(user.items()))
				title = entryData["title"]
				if principal == title:
					printl("", self, "C")
					userId = entryData["id"]

					xmlResponse = plexInstance.switchUser(userId, credential)

					entryData = (dict(xmlResponse.items()))
					authenticationToken = entryData["authenticationToken"]
					myId = entryData["id"]

					foundMatchingUser = True
					break
			if foundMatchingUser:
				return True, {AuthorizationResult.PRINCIPAL: principal, AuthorizationResult.CREDENTIALS: authenticationToken, AuthorizationResult.ID: myId}
			else:
				return False, {AuthorizationResult.PRINCIPAL: principal, AuthorizationResult.ERROR: _("The user was not found!")}
		else:
			return False, {AuthorizationResult.PRINCIPAL: principal, AuthorizationResult.ERROR: _("Unauthorized")}

	def setupServer(self, config: list[ConfigElement]) -> dict[str, Any]:
		separator = "".ljust(250, "_")

		res: dict[str, Any] = {}

		config.append(getConfigListEntry(_("General Settings ") + separator, self._settings.about.getConfigElement(), _("-")))
		##
		config.append(getConfigListEntry(_(" > State"), self._state.getConfigElement(),
											   _("Toggle state to on/off to show this server in lost or not.")))
		config.append(getConfigListEntry(_(" > Autostart"), self._autostart.getConfigElement(),
											   _("Enter this server automatically on startup.")))
		config.append(getConfigListEntry(_(" > Name"), self._name.getConfigElement(), _("Simply a name for better overview")))
		config.append(getConfigListEntry(_(" > Trailer"), self._loadExtraData.getConfigElement(),
											   _("Enable trailer function. Only works with PlexPass or YYTrailer plugin.")))

		##
		config.append(getConfigListEntry(_("Connection Settings ") + separator, self._settings.about.getConfigElement(), _(" ")))
		##
		config.append(getConfigListEntry(_(" > Connection Type"), self._connectionType.getConfigElement(),
											   _("Select your type how the box is reachable.")))

		add_my_plex_settings = False
		if self._connectionType.getValue() == _CONNECTION_TYPE_IP or self._connectionType.getValue() == _CONNECTION_TYPE_DNS:  # IP or DNS
			config.append(getConfigListEntry(_(" > Local Authentication"), self._localAuth.getConfigElement(),
												   _("Use this if you secured your plex server in the settings.")))
			if self._connectionType.getValue() == _CONNECTION_TYPE_IP:
				config.append(getConfigListEntry(_(" >> IP"), self._ip.getConfigElement(), _(" ")))
				config.append(getConfigListEntry(_(" >> Port"), self._port.getConfigElement(), _(" ")))
			else:
				config.append(getConfigListEntry(_(" >> DNS"), self._dns.getConfigElement(), _(" ")))
				config.append(getConfigListEntry(_(" >> Port"), self._port.getConfigElement(), _(" ")))
			if self._localAuth.getValue():
				add_my_plex_settings = True

		elif self._connectionType.getValue() == _CONNECTION_TYPE_PLEX_TV:  # plex.tv
			add_my_plex_settings = True

		if add_my_plex_settings:
			config.append(getConfigListEntry(_(" >> plex.tv URL"), self._myplexUrl.getConfigElement(), ''))
			config.append(getConfigListEntry(_(" >> plex.tv Username"), self._myplexUsername.getConfigElement(), ''))
			config.append(getConfigListEntry(_(" >> plex.tv Password"), self._myplexPassword.getConfigElement(), ''))

			config.append(getConfigListEntry(_(" >> plex.tv Home Users"), self._myplexHomeUsers.getConfigElement(), _("Use Home Users?")))
			if self._myplexHomeUsers.getValue():
				config.append(getConfigListEntry(_(" >> Use Settings Protection"), self._protectSettings.getConfigElement(),
													   _("Ask for pin?")))
				if self._protectSettings.getValue():
					config.append(getConfigListEntry(_(" >> Settings Pincode"), self._settingsPin.getConfigElement(),
														   _("Pincode for changing settings")))

				config.append(getConfigListEntry(_(" >> plex.tv Pin Protection"), self._myplexPinProtect.getConfigElement(),
													   _("Use Pinprotection for switch back to plex.tv user?")))
				if self._myplexPinProtect.getValue():
					config.append(getConfigListEntry(_(" >> plex.tv Pincode"), self._myplexPin.getConfigElement(),
														   _("Pincode for switching back from any home user.")))
		##
		config.append(getConfigListEntry(_("Playback Settings ") + separator, self._settings.about.getConfigElement(), _(" ")))
		##

		config.append(getConfigListEntry(_(" > Playback Type"), self._playbackType.getConfigElement(), _(" ")))
		if self._playbackType.getValue() == "0":
			res["useMappings"] = False

		elif self._playbackType.getValue() == "1":
			res["useMappings"] = False
			config.append(getConfigListEntry(_(" >> Use universal Transcoder"), self._universalTranscoder.getConfigElement(),
												   _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
			if not self._universalTranscoder.getValue():
				config.append(getConfigListEntry(_(" >> Transcoding quality"), self._quality.getConfigElement(),
													   _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
				config.append(getConfigListEntry(_(" >> Segmentsize in seconds"), self._segments.getConfigElement(),
													   _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))
			else:
				config.append(getConfigListEntry(_(" >> Transcoding quality"), self._uniQuality.getConfigElement(),
													   _("You need gstreamer_fragmented installed for this feature! Please check in System ... ")))

		elif self._playbackType.getValue() == "2":
			res["useMappings"] = True
			config.append(getConfigListEntry(_("> Search and use forced subtitles"), self._useForcedSubtitles.getConfigElement(),
								   _("Monitor playback to activate subtitles automatically if needed. You have to enable subtitles with 'Text'-Buttion first.")))

		elif self._playbackType.getValue() == "3":
			res["useMappings"] = False
		# config.append(getConfigListEntry(_(">> Username"), self._smbUser.getConfigElement()))
		# config.append(getConfigListEntry(_(">> Password"), self._smbPassword.getConfigElement()))
		# config.append(getConfigListEntry(_(">> Server override IP"), self._nasOverrideIp.getConfigElement()))
		# config.append(getConfigListEntry(_(">> Servers root"), self._nasRoot.getConfigElement()))

		if self._playbackType.getValue() == "2":
			##
			config.append(
				getConfigListEntry(_("Subtitle Settings ") + separator, self._settings.about.getConfigElement(), _(" ")))
			##
			config.append(getConfigListEntry(_(" >> Enable Subtitle renaming in direct local mode"),
												   self._srtRenamingForDirectLocal.getConfigElement(),
												   _("Renames filename.eng.srt automatically to filename.srt so e2 is able to read them.")))
			if self._srtRenamingForDirectLocal.getValue():
				config.append(
					getConfigListEntry(_(" >> Target subtitle language"), self._subtitlesLanguage.getConfigElement(),
									   _("Search string that should be removed from srt file.")))

		self._appendWakeOnLanConfigList(config, separator)

		##
		config.append(getConfigListEntry(_("Sync Settings ") + separator, self._settings.about.getConfigElement(), _(" ")))
		##
		config.append(getConfigListEntry(_(" > Sync Movies Medias"), self._syncMovies.getConfigElement(), _("Sync this content.")))
		config.append(getConfigListEntry(_(" > Sync Shows Medias"), self._syncShows.getConfigElement(), _("Sync this content.")))
		config.append(getConfigListEntry(_(" > Sync Music Medias"), self._syncMusic.getConfigElement(), _("Sync this content.")))

		if self._myplexHomeUsers.getValue():
			res["useHomeUsers"] = True
		else:
			res["useHomeUsers"] = False

		return res

	def _writeValue(self, value: T) -> None:
		pass

	def _readValue(self) -> T:
		pass

class PlexMappingSettings(AbstractMappingSettings['PlexMappingSettings']):
	def __init__(self, owner: SettingsStorage, parent: Element = None):
		super().__init__(owner, parent)

	def _writeValue(self, value: 'PlexMappingSettings') -> None:
		pass

	def _readValue(self) -> 'PlexMappingSettings':
		pass

class PlexUsersSettings(AbstractUserSettings['PlexUsersSettings']):
	def __init__(self, owner: SettingsStorage, parent: Element = None):
		super().__init__(owner, parent)

	def _writeValue(self, value: T) -> None:
		pass

	def _readValue(self) -> T:
		pass

class PlexSettingsFactory(AbstractServerSettingsFactory[PlexSettings]):
	def __init__(self):
		super().__init__()
		pass

	def createServerSettings(self, owner: SettingsStorage, parent: Element = None) -> AbstractServerSettings[T]:
		return PlexSettings(owner, parent)

	def createEmptyServerSettings(self, owner: "SettingsStorage", data: DiscoveredServer) -> AbstractServerSettings[T]:
		plex: PlexSettings = PlexSettings(owner)
		plex.name().setValue(data.serverName)
		plex.ip().setValue(data.server)
		plex.port().setValue(int(data.port))
		plex.id().setValue(owner.getUniqueId())

		return plex

	def createNewMapping(self, server: PlexSettings, idMapping: str, remotePath: str, localPath: str) -> PlexMappingSettings:
		res: PlexMappingSettings = PlexMappingSettings(server._settings)
		res.id.setValue(idMapping)
		res.remotePath.setValue(remotePath)
		res.localPath.setValue(localPath)
		return res

	def createNewUser(self, server: 'AbstractServerSettings[T]', idUser: str, username: str, pin: str, token: str) -> PlexUsersSettings:
		res: PlexUsersSettings = PlexUsersSettings(server._settings)
		res.id.setValue(idUser)
		res.username.setValue(username)
		res.pin.setValue(pin)
		res.token.setValue(token)
		return res

	def createMediaLibrary(self, session, server: PlexSettings):
		# imported here to avoid a circular import at module load time
		from .DP_PlexLibrary import PlexLibrary
		return PlexLibrary(session, server)

	def createHeader(self, g_sessionID, asDict=True):
		printl2("", "__common__::getPlexHeader", "S")

		boxData = getBoxInformation()
		instance: Singleton = Singleton()
		boxName = instance.getSettingsInstance().boxName.getValue()

		# why do we use ios!!!!! instead of enigma
		# Unable to find client profile for device; platform=Enigma, platformVersion=oe20, device=Dreambox, model=500hd
		# ERROR - [TranscodeUniversalRequest] Unable to find a matching profile

		if asDict:
			plexHeader = {'X-Plex-Platform': "iOS",
						  'X-Plex-Platform-Version': boxData[3],
						  'X-Plex-Provides': "player",
						  'X-Plex-Product': "DreamPlex",
						  'X-Plex-Version': getVersion(),
						  'X-Plex-Device': boxData[0],
						  'X-Plex-Device-Name': boxName,
						  'X-Plex-Model': boxData[1],
						  'X-Plex-Client-Identifier': g_sessionID,
						  'X-Plex-Client-Platform': "iOS"}
		else:
			plexHeader = []
			plexHeader.append('X-Plex-Platform:iOS')  # + boxData[2]) # arch
			plexHeader.append('X-Plex-Platform-Version:' + boxData[3])  # version
			plexHeader.append('X-Plex-Provides:player')
			plexHeader.append('X-Plex-Product:DreamPlex')
			plexHeader.append('X-Plex-Version:' + getVersion())
			plexHeader.append('X-Plex-Device:' + boxData[0])  # manu
			plexHeader.append("X-Plex-Device-Name:" + boxName)
			plexHeader.append("X-Plex-Model:" + boxData[1])  # model
			plexHeader.append('X-Plex-Client-Identifier:' + g_sessionID)
			plexHeader.append("X-Plex-Client-Platform:iOS")

		printl2("", "__common__::getPlexHeader", "C")
		return plexHeader

	def getServerHeaders(self):
		instance: Singleton = Singleton()

		plexHeader = {
			"Content-type": "application/x-www-form-urlencoded",
			"X-Plex-Version": getVersion(),
			"X-Plex-Client-Identifier": getUUID(),
			"X-Plex-Provides": "player",
			"X-Plex-Product": "DreamPlex",
			"X-Plex-Device-Name": instance.getSettingsInstance().boxName.getValue(),
			"X-Plex-Platform": "Enigma2",
			"X-Plex-Model": "Enigma2",
			"X-Plex-Device": "stb",
		}
		return plexHeader




