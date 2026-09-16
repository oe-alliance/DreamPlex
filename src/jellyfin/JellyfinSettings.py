from __future__ import annotations
from typing import Any
from xml.etree.ElementTree import Element, SubElement
import json
from http.client import HTTPConnection

from .. import AbstractServerSettingsFactory, Singleton
from .. import DPH_Vault
from ..__common__ import EntryServer, DiscoveredServer, printl2 as printl, getVersion, getUUID, \
	testMediaServerConnectivity, testInetConnectivity
from .. import _

from Components.config import ConfigInteger, ConfigYesNo, ConfigText, ConfigSelection, ConfigIP, \
	ConfigElement, getConfigListEntry
from ..DP_SettingsStorage import SettingsStorage, BaseSettings, AbstractServerSettings, SERVER_SETTINGS_ELEMENT_NAME, \
	SERVER_SETTINGS_TYPE_ATTRIBUTE_NAME, AuthorizationMode, AuthorizationResult, AbstractMappingSettings, \
	AbstractUserSettings, T, USER_SWITCH_LOCAL_PROFILES


def buildAuthorizationHeaderValue(token: str | None = None) -> str:
	"""Builds the value for the "Authorization" HTTP header Jellyfin expects
	- the only auth mechanism still accepted from server 12.0 on, which
	removed X-Emby-Authorization/X-Emby-Token/X-MediaBrowser-Token and the
	?api_key= query parameter entirely (EnableLegacyAuthorization defaults
	to disabled there). This exact "Authorization: MediaBrowser ..." scheme
	has been supported since at least Jellyfin 10.8, so there is nothing
	version-specific here - one implementation covers every server this
	plugin talks to, old and new."""
	value = 'MediaBrowser Client="DreamPlex", Device="Enigma2", DeviceId="' + getUUID() + '", Version="' + getVersion() + '"'
	if token:
		value += ', Token="' + token + '"'
	return value


class _DeviceEncryptedText(BaseSettings[str, ConfigText]):
	"""A BaseSettings[str, ConfigText] whose on-disk XML text is masked with
	DPH_Vault's device-derived key, transparently to everything else.

	getValue()/setValue() (inherited from BaseSettings) go through
	self._delegate.value - the in-memory ConfigText the settings screen
	actually edits - which stays plain text the whole time, so the "Password"
	field in DreamPlex's UI looks and behaves exactly as before. Only
	_writeValue()/_readValue(), the two methods that talk to the XML element,
	are overridden here: that is the one place BaseSettings serializes to and
	from disk, so it is the only place that needs to know encryption exists
	at all.
	"""

	def _writeValue(self, value: str) -> None:
		super()._writeValue(DPH_Vault.encryptDevice(value) if value else value)

	def _readValue(self) -> str:
		stored = super()._readValue()
		if stored and DPH_Vault.isEncrypted(stored):
			decrypted = DPH_Vault.decryptDevice(stored)
			# decrypted is None only if the device key changed since this was
			# written (box swapped, network interface changed, settings.xml
			# moved to different hardware) - surface the still-encrypted blob
			# rather than silently losing the value: the caller compares it
			# against a real password all the same, which will simply fail
			# and end up asking the user to re-enter it, exactly as it should.
			return decrypted if decrypted is not None else stored
		return stored


class JellyfinSettings(AbstractServerSettings["JellyfinSettings"]):
	SETTINGS_NAME: str = "JellyfinServer"

	def __init__(self, owner: SettingsStorage, parent: Element = None):
		if not parent:
			parent = Element(SERVER_SETTINGS_ELEMENT_NAME, {SERVER_SETTINGS_TYPE_ATTRIBUTE_NAME: self.SETTINGS_NAME})
		super().__init__(owner, parent)

		default_name = "JellyfinServer"
		default_ip = [192, 168, 0, 1]
		default_port = 8096

		# SERVER SETTINGS
		self._id = BaseSettings[int, ConfigInteger]("id", ConfigInteger(default=-1), owner, parent)
		self._state = BaseSettings[bool, ConfigYesNo]("state", ConfigYesNo(default=True), owner, parent)
		self._autostart = BaseSettings[bool, ConfigYesNo]("autostart", ConfigYesNo(), owner, parent)
		self._name = BaseSettings[str, ConfigText]("name", ConfigText(default=default_name, visible_width=50, fixed_size=False), owner, parent)
		self._connectionType = BaseSettings[str, ConfigSelection]("connectionType", ConfigSelection(default="0",
																								choices=[("0", _("IP")),
																										 ("1", _("DNS"))]), owner, parent)
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
		self._loadExtraData = BaseSettings[str, ConfigSelection]("loadExtraData", ConfigSelection(default="0", choices=[("0", "None"), ("1", "Extras")]), owner, parent)

		self._srtRenamingForDirectLocal = BaseSettings[bool, ConfigYesNo]("srtRenamingForDirectLocal", ConfigYesNo(), owner, parent)
		self._subtitlesLanguage = BaseSettings[str, ConfigText]("subtitlesLanguage", ConfigText(default="de", visible_width=10, fixed_size=False), owner, parent)
		self._useForcedSubtitles = BaseSettings[bool, ConfigYesNo]("useForcedSubtitles", ConfigYesNo(default=True), owner, parent)

		printl("=== SERVER SETTINGS ===", "JellyfinSettings::__init__", "D")
		printl("Server Settings: ", "JellyfinSettings::__init__", "D")
		printl("id: " + str(self._id.getValue()), "JellyfinSettings::__init__", "D")
		printl("state: " + str(self._state.getValue()), "JellyfinSettings::__init__", "D")
		printl("autostart: " + str(self._autostart.getValue()),"JellyfinSettings::__init__", "D")
		printl("name: " + str(self._name.getValue()), "JellyfinSettings::__init__", "D")
		printl("connectionType: " + str(self._connectionType.getValue()), "JellyfinSettings::__init__", "D")
		printl("ip: " + str(self._ip.getValue()), "JellyfinSettings::__init__", "D")
		printl("dns: " + str(self._dns.getValue()), "JellyfinSettings::__init__", "D")
		printl("port: " + str(self._port.getValue()), "JellyfinSettings::__init__", "D")
		printl("playbackType: " + str(self._playbackType.getValue()), "JellyfinSettings::__init__", "D")

		# Jellyfin authentication
		self._username = BaseSettings[str, ConfigText]("username", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		# This is the "default"/server-level login, entered once when the
		# server is set up - unlike a saved profile's password (JellyfinUsers
		# Settings.password, in JellyfinLibrary.py), there is no PIN tied to
		# it to derive a key from, so it is masked with the device-derived
		# key instead (see DPH_Vault.encryptDevice / _DeviceEncryptedText
		# above) - weaker than PIN-derived encryption, but still not
		# plaintext-on-disk.
		self._password = _DeviceEncryptedText("password", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._apiKey = BaseSettings[str, ConfigText]("apiKey", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._accessToken = BaseSettings[str, ConfigText]("accessToken", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._userId = BaseSettings[str, ConfigText]("userId", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		self._deviceId = BaseSettings[str, ConfigText]("deviceId", ConfigText(visible_width=50, fixed_size=False), owner, parent)

		printl("=== JELLYFIN AUTH ===", "JellyfinSettings::__init__", "D")
		printl("username: " + str(self._username.getValue()), "JellyfinSettings::__init__", "D", True, 8)
		printl("password: " + str(self._password.getValue()), "JellyfinSettings::__init__", "D", True, 6)
		printl("apiKey: " + str(self._apiKey.getValue()), "JellyfinSettings::__init__", "D", True, 8)
		printl("accessToken: " + str(self._accessToken.getValue()), "JellyfinSettings::__init__", "D", True, 8)
		printl("userId: " + str(self._userId.getValue()), "JellyfinSettings::__init__", "D", True, 8)
		printl("deviceId: " + str(self._deviceId.getValue()), "JellyfinSettings::__init__", "D", True, 8)

		# TRANSCODED
		self._universalTranscoder = BaseSettings[bool, ConfigYesNo]("universalTranscoder", ConfigYesNo(default=True), owner, parent)
		self._quality = BaseSettings[str, ConfigSelection]("quality", ConfigSelection(default="7",
																			  choices=[("0", _("64kbps, 128p, 3fps")),
																					   ("1", _("96kbps, 128p, 12fps")),
																					   ("2", _("208kbps, 160p, 15fps")),
																					   ("3", _("320kbps, 240p, 15fps")),
																					   ("4", _("720kbps, 320p, 30fps")),
																					   ("5", _("1.5Mbps, 480p, 30fps")),
																					   ("6", _("2Mbps, 720p, 30fps")),
																					   ("7", _("4Mbps, 720p, 30fps")),
																					   ("8", _("8Mbps, 1080p, 30fps")),
																					   ("9", _("10Mbps, 1080p, 30fps")),
																					   ("10", _("12Mbps, 1080p, 30fps")),
																					   ("11", _("20Mbps, 1080p, 30fps")),
																		   ("12", _("Original Quality"))]), owner, parent)

		# Preferenze Audio/Sottotitoli
		self._subtitlesLanguage = BaseSettings[str, ConfigText]("subtitlesLanguage", ConfigText(default="", visible_width=10, fixed_size=False), owner, parent)
		self._useForcedSubtitles = BaseSettings[bool, ConfigYesNo]("useForcedSubtitles", ConfigYesNo(default=True), owner, parent)
		self._audioLanguage = BaseSettings[str, ConfigText]("audioLanguage", ConfigText(default="", visible_width=10, fixed_size=False), owner, parent)
		self._subtitleMethod = BaseSettings[str, ConfigSelection](
			"subtitleMethod",
			ConfigSelection(default="External", choices=[("External", _("External")), ("Embed", _("Embed"))])
		, owner, parent)
		# bitrate massimo custom (0 = auto dal profilo qualità)
		self._customMaxBitrate = BaseSettings[int, ConfigInteger]("customMaxBitrate", ConfigInteger(default=0, limits=(0, 200000000)), owner, parent)
		# Temporary overrides for immediate track selection (values >= 0 are applied once)
		self._overrideAudioIndex = BaseSettings[int, ConfigInteger]("overrideAudioIndex", ConfigInteger(default=-1, limits=(-1, 100)), owner, parent)
		self._overrideSubtitleIndex = BaseSettings[int, ConfigInteger]("overrideSubtitleIndex", ConfigInteger(default=-1, limits=(-1, 100)), owner, parent)

		printl("subtitlesLanguage: " + str(self._subtitlesLanguage.getValue()), "JellyfinSettings::__init__", "D")
		printl("useForcedSubtitles: " + str(self._useForcedSubtitles.getValue()), "JellyfinSettings::__init__", "D")
		printl("audioLanguage: " + str(self._audioLanguage.getValue()), "JellyfinSettings::__init__", "D")
		printl("subtitleMethod: " + str(self._subtitleMethod.getValue()), "JellyfinSettings::__init__", "D")
		printl("customMaxBitrate: " + str(self._customMaxBitrate.getValue()), "JellyfinSettings::__init__", "D")
		printl("overrideAudioIndex: " + str(self._overrideAudioIndex.getValue()), "JellyfinSettings::__init__", "D")
		printl("overrideSubtitleIndex: " + str(self._overrideSubtitleIndex.getValue()), "JellyfinSettings::__init__", "D")

		# WOL fields/accessors are declared once on AbstractServerSettings
		# (see DP_SettingsStorage.py) - identical for every backend.

		# Carica eventuali utenti Jellyfin dal nodo XML
		try:
			usersElem = self._parent.find('users') if self._parent is not None else None
			if usersElem is not None:
				for userElem in list(usersElem.findall('user')):
					u = JellyfinUsersSettings(owner, parent=userElem)
					# force-read the values from the node. Do not call this
					# throwaway variable "_": this method also calls the
					# translation function _(), and assigning to a name
					# anywhere in a function makes Python treat it as local
					# for the whole function body, breaking every _("...")
					# call above this point with UnboundLocalError.
					_discard = u.id.getValue(); _discard = u.username.getValue(); _discard = u.pin.getValue(); _discard = u.token.getValue()
					self._users.append(u)
		except Exception:
			pass

	def getIndex(self) -> int | None:
		return self._id.getValue()

	def getName(self) -> str | None:
		return self._name.getValue()

	def getType(self) -> str:
		return self.SETTINGS_NAME

	def getUserSwitchMode(self) -> str:
		return USER_SWITCH_LOCAL_PROFILES

	def getCurrentUserDisplayName(self) -> str | None:
		return self._username.getValue() or None

	def getCurrentUserAccessToken(self) -> str | None:
		return self._accessToken.getValue() or None

	def getCloneExcludeFields(self) -> set[str]:
		return {"_id", "_username", "_password", "_apiKey", "_accessToken", "_userId", "_deviceId"}

	def isActive(self) -> bool:
		return self._state.getValue()

	def isAutostart(self) -> bool:
		return self._autostart.getValue()

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
		# Jellyfin has no plex.tv-style cloud relay - only IP direct or DNS.
		if str(self._connectionType.getValue()) == "0":
			ip = "%d.%d.%d.%d" % tuple(self._ip.getValue())
			port = int(self._port.getValue())
			return testMediaServerConnectivity(ip, port)
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

	def username(self) -> BaseSettings[str, ConfigText]:
		return self._username

	def password(self) -> BaseSettings[str, ConfigText]:
		return self._password

	def apiKey(self) -> BaseSettings[str, ConfigText]:
		return self._apiKey

	def accessToken(self) -> BaseSettings[str, ConfigText]:
		return self._accessToken

	def userId(self) -> BaseSettings[str, ConfigText]:
		return self._userId

	def deviceId(self) -> BaseSettings[str, ConfigText]:
		return self._deviceId

	def universalTranscoder(self) -> BaseSettings[bool, ConfigYesNo]:
		return self._universalTranscoder

	def quality(self) -> BaseSettings[str, ConfigSelection]:
		return self._quality

	def audioLanguage(self) -> BaseSettings[str, ConfigText]:
		return self._audioLanguage

	def subtitleMethod(self) -> BaseSettings[str, ConfigSelection]:
		return self._subtitleMethod

	def customMaxBitrate(self) -> BaseSettings[int, ConfigInteger]:
		return self._customMaxBitrate

	def overrideAudioIndex(self) -> BaseSettings[int, ConfigInteger]:
		return self._overrideAudioIndex

	def overrideSubtitleIndex(self) -> BaseSettings[int, ConfigInteger]:
		return self._overrideSubtitleIndex

	def toEntryServer(self) -> EntryServer | None:
		if self._connectionType.getValue() == "0":
			host = "%d.%d.%d.%d" % tuple(self._ip.getValue())
		else:
			host = self._dns.getValue()

		return EntryServer(name=self.getName(),
							serverHost=host,
							serverPort="%d" % self._port.getValue(),
							username=None,
							active=str(self._state.getValue()),
							settings=self)

	def requireAuthentication(self) -> bool:
		return True

	def pinRequired(self) -> bool:
		return False

	def checkPin(self, pin: str) -> bool:
		return True

	def supportServerMapping(self) -> bool:
		return True

	def listSupportedServerMappings(self, session) -> list[str] | None:
		return None

	def supportUsers(self) -> bool:
		# Jellyfin supports multiple users; we use username/password instead of the PIN
		return True

	def registerServer(self, session) -> bool:
		# imported here to avoid a circular import at module load time
		from .JellyfinLibrary import JellyfinLibrary
		jellyfinInstance = Singleton().getMediaLibrary(JellyfinLibrary(session, self))

		# /System/Info/Public needs no authentication, so it is enough to
		# confirm the host/port actually point at a reachable Jellyfin server
		# before letting the user save it.
		info = jellyfinInstance._request_json("GET", "/System/Info/Public")

		if info is None:
			return False

		self._machineIdentifier.setValue(info.get("Id", ""))
		printl("machineIdentifier: " + str(self._machineIdentifier.getValue()), self, "D")

		return True

	def buildAuthorization(self, session, mode: AuthorizationMode) -> tuple[bool, dict[AuthorizationResult, str]]:
		result: dict[AuthorizationResult, str] = {}

		# Priorità: token già presente, altrimenti API key, altrimenti username/password
		token = self._accessToken.getValue()
		if token:
			result[AuthorizationResult.PRINCIPAL] = self._username.getValue() or ""
			result[AuthorizationResult.CREDENTIALS] = token
			if self._userId.getValue():
				result[AuthorizationResult.ID] = self._userId.getValue()
			return True, result

		api_key = self._apiKey.getValue()
		if api_key:
			result[AuthorizationResult.PRINCIPAL] = self._username.getValue() or "api-key"
			result[AuthorizationResult.CREDENTIALS] = api_key
			return True, result

		# Try to authenticate in REMOTE mode if we have username/password but no token
		if self._username.getValue() and self._password.getValue():
			if mode == AuthorizationMode.REMOTE:
				ok, info = self.authenticateUser(session, self._username.getValue(), self._password.getValue())
				if ok:
					return ok, info
				else:
					# restituisci l'errore di autenticazione
					return False, info
			# fallback: restituiamo username/password (per flussi che chiedono di inserirli manualmente)
			result[AuthorizationResult.PRINCIPAL] = self._username.getValue()
			result[AuthorizationResult.CREDENTIALS] = self._password.getValue()
			return True, result

		result[AuthorizationResult.ERROR] = _("No authentication credentials provided")
		result[AuthorizationResult.PRINCIPAL] = self._username.getValue() or ""
		return False, result

	def authenticateUser(self, session, principal: str, credential: str) -> tuple[bool, dict[AuthorizationResult, str]]:
		result: dict[AuthorizationResult, str] = {}

		username = principal
		password = credential

		if not username or not password:
			result[AuthorizationResult.ERROR] = _("Invalid credentials")
			result[AuthorizationResult.PRINCIPAL] = username or ""
			return False, result

		# Costruzione host/porta da impostazioni
		host: str
		if self._connectionType.getValue() == "0":  # IP
			ip_list = self._ip.getValue()
			try:
				host = "%d.%d.%d.%d" % tuple(ip_list)
			except Exception:
				host = ""  # fallback
		else:
			host = self._dns.getValue()

		port = int(self._port.getValue()) if self._port.getValue() else 8096

		try:
			conn = HTTPConnection(host, port, timeout=10)
			headers = JellyfinSettingsFactory().getServerHeaders()
			headers['Content-Type'] = 'application/json'
			payload = json.dumps({
				"Username": username,
				"Pw": password
			})
			conn.request("POST", "/Users/AuthenticateByName", body=payload, headers=headers)
			resp = conn.getresponse()
			raw = resp.read().decode('utf-8') if resp else ''
			if resp and resp.status in (200, 204):
				data = json.loads(raw) if raw else {}
				token = data.get('AccessToken') or data.get('Token') or ''
				user = data.get('User') or {}
				user_id = user.get('Id') or ''

				if token and user_id:
					# Salva nelle impostazioni
					self._username.setValue(username)
					self._password.setValue(password)
					self._accessToken.setValue(token)
					self._userId.setValue(user_id)
					# update/add the user in the persisted list
					try:
						self.addOrUpdateUser(username, user_id, token, password)
					except Exception:
						pass
					self._settings.writeToFile()
					return True, {
						AuthorizationResult.PRINCIPAL: username,
						AuthorizationResult.CREDENTIALS: token,
						AuthorizationResult.ID: user_id
					}
				else:
					result[AuthorizationResult.ERROR] = _("Malformed response from server")
					result[AuthorizationResult.PRINCIPAL] = username
					return False, result
			else:
				# Prova a leggere messaggio d'errore
				try:
					data = json.loads(raw)
					msg = data.get('Message') or raw
				except Exception:
					msg = raw or (str(resp.status) if resp else "error")
				result[AuthorizationResult.ERROR] = msg
				result[AuthorizationResult.PRINCIPAL] = username
				return False, result
		except Exception as e:
			result[AuthorizationResult.ERROR] = str(e)
			result[AuthorizationResult.PRINCIPAL] = username
			return False, result

	def setupServer(self, config: list[ConfigElement]) -> dict[str, Any]:
		separator = "".ljust(250, "_")
		res: dict[str, Any] = {}

		# General settings
		config.append(getConfigListEntry(_("General Settings ") + separator, self._settings.about.getConfigElement(), _("-")))
		config.append(getConfigListEntry(_(" > State"), self._state.getConfigElement(), _("Toggle on/off to show or hide this server.")))
		config.append(getConfigListEntry(_(" > Autostart"), self._autostart.getConfigElement(), _("Enter this server automatically on startup.")))
		config.append(getConfigListEntry(_(" > Name"), self._name.getConfigElement(), _("A friendly name for this server.")))

		# Connection settings
		config.append(getConfigListEntry(_("Connection Settings ") + separator, self._settings.about.getConfigElement(), " "))
		config.append(getConfigListEntry(_(" > Connection Type"), self._connectionType.getConfigElement(), _("Select IP or DNS.")))
		if self._connectionType.getValue() == "0":
			config.append(getConfigListEntry(_(" >> IP"), self._ip.getConfigElement(), " "))
			config.append(getConfigListEntry(_(" >> Port"), self._port.getConfigElement(), " "))
		else:
			config.append(getConfigListEntry(_(" >> DNS"), self._dns.getConfigElement(), " "))
			config.append(getConfigListEntry(_(" >> Port"), self._port.getConfigElement(), " "))

		# Authentication (facoltativa: username/password oppure API key)
		config.append(getConfigListEntry(_("Authentication ") + separator, self._settings.about.getConfigElement(), " "))
		config.append(getConfigListEntry(_(" > Username"), self._username.getConfigElement(), _("Username for Jellyfin account.")))
		config.append(getConfigListEntry(_(" > Password"), self._password.getConfigElement(), _("Password for Jellyfin account.")))
		config.append(getConfigListEntry(_(" > API Key (optional)"), self._apiKey.getConfigElement(), _("If present, it will be used instead of username/password.")))

		# Playback settings
		config.append(getConfigListEntry(_("Playback Settings ") + separator, self._settings.about.getConfigElement(), " "))
		config.append(getConfigListEntry(_(" > Playback Type"), self._playbackType.getConfigElement(), " "))
		# Transcode quality options
		config.append(getConfigListEntry(_(" >> Transcoding quality"), self._quality.getConfigElement(), _("Affects MaxStreamingBitrate for playback.")))
		# Subtitles/Audio prefs
		config.append(getConfigListEntry(_(" >> Subtitles language (e.g. it,en)"), self._subtitlesLanguage.getConfigElement(), _("Preferred subtitles language.")))
		config.append(getConfigListEntry(_(" >> Use forced subtitles"), self._useForcedSubtitles.getConfigElement(), _("Prefer forced subtitles if available.")))
		config.append(getConfigListEntry(_(" >> Audio language (optional)"), self._audioLanguage.getConfigElement(), _("Preferred audio language, fallback to subtitles language.")))
		config.append(getConfigListEntry(_(" >> Subtitle method"), self._subtitleMethod.getConfigElement(), _("Choose how to deliver subtitles (External/Embed).")))
		config.append(getConfigListEntry(_(" >> Custom Max Bitrate (0 = auto)"), self._customMaxBitrate.getConfigElement(), _("Override bitrate from quality profile.")))

		self._appendWakeOnLanConfigList(config, separator)

		# Jellyfin: no mappings/home users section (non necessario)
		res["useMappings"] = False
		res["useHomeUsers"] = False

		return res

	# -------------------------------------------------
	# Gestione utenti Jellyfin persistenti (XML)
	# -------------------------------------------------
	def _ensureUsersElement(self) -> Element:
		usersElem = self._parent.find('users') if self._parent is not None else None
		if usersElem is None and self._parent is not None:
			usersElem = SubElement(self._parent, 'users')
		return usersElem

	def addOrUpdateUser(self, username: str, user_id: str, token: str, password: str = "") -> None:
		usersElem = self._ensureUsersElement()
		if usersElem is None:
			return
		# Cerca se esiste già lo user per id o username
		foundElem = None
		for ue in list(usersElem.findall('user')):
			uid = (ue.find('id').text if ue.find('id') is not None else None)
			uname = (ue.find('username').text if ue.find('username') is not None else None)
			if uid == str(user_id) or (uname and uname == username):
				foundElem = ue
				break
		if foundElem is None:
			foundElem = SubElement(usersElem, 'user')
			SubElement(foundElem, 'id').text = str(user_id)
			SubElement(foundElem, 'username').text = username
			SubElement(foundElem, 'pin').text = ""  # nessun PIN finché l'utente non lo imposta esplicitamente
			SubElement(foundElem, 'token').text = token
			SubElement(foundElem, 'password').text = password or ""
			# create the user object and add it to the runtime list
			u = JellyfinUsersSettings(self._settings, parent=foundElem)
			self._users.append(u)
		else:
			# aggiorna username sempre
			xe = foundElem.find('username')
			if xe is not None:
				xe.text = username
			# Se il profilo esistente ha token/password cifrati con un PIN,
			# non sovrascriverli qui in chiaro: questo metodo non ha il PIN a
			# disposizione per ricifrarli. Il refresh del token per un
			# profilo protetto passa da JellyfinLibrary._tryRefreshToken(),
			# che il PIN ce l'ha e ricifra correttamente.
			te = foundElem.find('token')
			if te is None:
				te = SubElement(foundElem, 'token')
			if not DPH_Vault.isEncrypted(te.text):
				te.text = token
			pe = foundElem.find('password')
			if pe is None:
				pe = SubElement(foundElem, 'password')
			if not DPH_Vault.isEncrypted(pe.text):
				pe.text = password or pe.text or ""
		# scrivi su file
		self._settings.writeToFile()

	def _writeValue(self, value: T) -> None:
		pass

	def _readValue(self) -> T:
		pass


class JellyfinSettingsFactory(AbstractServerSettingsFactory["JellyfinSettings"]):
	def createServerSettings(self, owner: "SettingsStorage", parent: Element = None) -> JellyfinSettings:
		return JellyfinSettings(owner, parent)

	def createEmptyServerSettings(self, owner: "SettingsStorage", data: DiscoveredServer) -> JellyfinSettings:
		settings = JellyfinSettings(owner)
		# Usa i campi definiti in DiscoveredServer (__common__.py)
		if data.serverName:
			settings._name.setValue(data.serverName)
		if data.server:
			# Se server è un host/IP stringa, impostiamo in DNS se non è IP, altrimenti in IP
			try:
				parts = [int(p) for p in str(data.server).split('.')]
				if len(parts) == 4 and all(0 <= p <= 255 for p in parts):
					settings._connectionType.setValue("0")
					settings._ip.setValue(parts)
				else:
					settings._connectionType.setValue("1")
					settings._dns.setValue(str(data.server))
			except Exception:
				settings._connectionType.setValue("1")
				settings._dns.setValue(str(data.server))
		if data.port:
			settings._port.setValue(int(data.port))
		if data.uuid:
			settings._machineIdentifier.setValue(data.uuid)
		# assegna un id univoco
		try:
			settings._id.setValue(owner.getUniqueId())
		except Exception:
			pass
		return settings

	def createNewMapping(self, server: 'JellyfinSettings', idMapping: str, remotePath: str, localPath: str) -> AbstractMappingSettings["JellyfinSettings"]:
		# Create a new mapping for Jellyfin server
		# This would be implemented to create a new mapping between a remote path on the Jellyfin server
		# and a local path on the Enigma2 device
		# For now, return None as this is not fully implemented
		return None

	def createNewUser(self, server: 'JellyfinSettings', idUser: str, username: str, pin: str, token: str) -> AbstractUserSettings["JellyfinSettings"]:
		# Crea elemento XML <user> sotto <users> del server e restituisce il wrapper settings
		usersElem = server._parent.find('users') if server._parent is not None else None
		if usersElem is None and server._parent is not None:
			usersElem = SubElement(server._parent, 'users')
		if usersElem is None:
			return None
		userElem = SubElement(usersElem, 'user')
		SubElement(userElem, 'id').text = str(idUser)
		SubElement(userElem, 'username').text = username or ""
		SubElement(userElem, 'pin').text = pin or ""
		SubElement(userElem, 'token').text = token or ""
		SubElement(userElem, 'password').text = ""
		user = JellyfinUsersSettings(server._settings, parent=userElem)
		# force-read the values from the node and link into the runtime list.
		# See the note in JellyfinSettings.__init__ on why this must not be
		# called "_": it shadows the translation function for the whole method.
		_discard = user.id.getValue(); _discard = user.username.getValue(); _discard = user.pin.getValue(); _discard = user.token.getValue()
		server.listUsers().append(user)
		server.saveChanges()
		return user

	def createMediaLibrary(self, session, server: JellyfinSettings):
		from .JellyfinLibrary import JellyfinLibrary
		return JellyfinLibrary(session, server)

	def createHeader(self, g_sessionID, asDict=True):
		headers = {
			'Content-Type': 'application/json',
			'Accept': 'application/json',
			'Authorization': buildAuthorizationHeaderValue(g_sessionID)
		}

		if asDict:
			return headers
		else:
			headerStr = ""
			for key in headers:
				headerStr += key + ": " + headers[key] + "\r\n"
			return headerStr

	def getServerHeaders(self):
		jellyfinHeader = {
			"Content-type": "application/json",
			"Accept": "application/json",
			"Authorization": buildAuthorizationHeaderValue()
		}
		return jellyfinHeader


class JellyfinUsersSettings(AbstractUserSettings['JellyfinUsersSettings']):
	def __init__(self, owner: SettingsStorage, parent: Element = None):
		super().__init__(owner, parent)
		# Jellyfin-only: the token DreamPlex holds for a saved profile can
		# expire server-side (unlike Plex's), and there is no PIN unlock on
		# the Jellyfin server itself to fall back on - re-authenticating
		# needs this profile's own password, not whatever was last typed at
		# server level. Stored plaintext for a PIN-less profile, or as an
		# DPH_Vault.encrypt() blob for a PIN-protected one - same rule as
		# token, applied by the callers in DP_ServerMenu/JellyfinLibrary that
		# have the PIN in hand, not by this class.
		self._password = BaseSettings[str, ConfigText]("password", ConfigText(visible_width=50, fixed_size=False), owner, parent)
		# Forza i campi a puntare al nodo <user> come parent per persistenza corretta
		if parent is not None:
			try:
				self._id._parent = parent
				self._username._parent = parent
				self._pin._parent = parent
				self._token._parent = parent
				self._password._parent = parent
			except Exception:
				pass

	@property
	def password(self) -> 'BaseSettings[str, ConfigText]':
		return self._password

	def _writeValue(self, value: T) -> None:
		pass

	def _readValue(self) -> T:
		pass
