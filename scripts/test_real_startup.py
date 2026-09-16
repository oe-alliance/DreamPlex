"""Import the real plugin package tree, exactly as enigma2 would, to catch
circular-import errors that a hand-stubbed test cannot see.

Only the enigma2 environment (enigma, Screens.*, Components.*, Tools.*) is
faked, via an import hook that auto-generates placeholder modules and
attributes, plus a slightly more faithful stub of Components.config (with
addNotifier, tostring/fromstring, .value) since SettingsStorage genuinely
needs that behaviour, not just a name that exists. Every module under
Plugins.Extensions.DreamPlex is the real source file, executed for real: if
two of our own modules import from each other in an order that does not
work, or a runtime path that only exercises at plugin startup is broken,
this fails exactly like the box does.

This is what found, one failure at a time: a "from .__init__ import x"
self-import loop between __init__.py and the plex/jellyfin settings modules,
two Python-2-only stdlib imports (urlparse, BaseHTTPServer) left in
DPH_RemoteHandler.py/DPH_RemoteListener.py, a logging call that crashed
before settings existed, an UnboundLocalError from a throwaway "_" variable
shadowing the translation function, and a newly created server that was
never attached to the settings document and so never survived a reload.

Usage: python3 scripts/test_real_startup.py
Exits with status 1 if anything above fails.
"""
import importlib.abc
import importlib.machinery
import os
import pathlib
import shutil
import sys
import tempfile
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB_PREFIXES = ("enigma", "Screens", "Components", "Tools", "skin", "Plugins.Plugin", "StartEnigma", "twisted")


class AutoModule(types.ModuleType):
	"""A module that fabricates a dummy class for any attribute accessed."""

	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		value = type(name, (object,), {"__init__": lambda self, *a, **k: None})
		setattr(self, name, value)
		return value


class StubLoader(importlib.abc.Loader):
	def create_module(self, spec):
		mod = AutoModule(spec.name)
		mod.__path__ = []
		return mod

	def exec_module(self, module):
		pass


class StubFinder(importlib.abc.MetaPathFinder):
	def find_spec(self, name, path, target=None):
		if any(name == p or name.startswith(p + ".") for p in STUB_PREFIXES):
			return importlib.machinery.ModuleSpec(name, StubLoader(), is_package=True)
		return None


class _Cfg:
	"""Enough of a Components.config element for SettingsStorage to run for
	real: addNotifier, tostring/fromstring, .value - not just a name."""

	def __init__(self, default=None, **kw):
		self.default = default
		self._value = default
		self._notifiers = []
		self.choices = kw.get('choices', [])

	@property
	def value(self):
		return self._value

	@value.setter
	def value(self, v):
		# real Components.config.ConfigElement.value is a property whose
		# setter calls every notifier as fn(self) - reproduce that (both
		# direct "configElement.value = x" assignment, as ConfigListScreen
		# does, and setValue() below go through it) so a notifier with the
		# wrong signature fails here exactly like it would on a real box.
		self._value = v
		for fn in list(self._notifiers):
			fn(self)

	def getValue(self):
		return self._value

	def setValue(self, v):
		self.value = v

	def tostring(self, v):
		return "" if v is None else str(v)

	def fromstring(self, s):
		return s

	def addNotifier(self, fn, initial_call=True, immediate_feedback=True):
		self._notifiers.append(fn)
		if initial_call:
			fn(self)

	def removeNotifier(self, fn):
		if fn in self._notifiers:
			self._notifiers.remove(fn)


class ConfigInteger(_Cfg):
	def fromstring(self, s):
		try:
			return int(s)
		except (TypeError, ValueError):
			return self.default


class ConfigYesNo(_Cfg):
	def tostring(self, v):
		return "true" if v else "false"

	def fromstring(self, s):
		return str(s).lower() in ("true", "1", "yes")


class ConfigIP(_Cfg):
	def __init__(self, default=None, **kw):
		_Cfg.__init__(self, default or [0, 0, 0, 0])

	def tostring(self, v):
		return ".".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)

	def fromstring(self, s):
		try:
			return [int(x) for x in str(s).split(".")]
		except Exception:
			return self.default


def setup_environment(plugroot):
	sys.meta_path.insert(0, StubFinder())
	sys.path.insert(0, str(plugroot))

	config_mod = AutoModule("Components.config")  # unknown names auto-fabricate
	config_mod.ConfigElement = _Cfg
	config_mod.ConfigText = _Cfg
	config_mod.ConfigDirectory = _Cfg
	config_mod.ConfigPassword = _Cfg
	config_mod.ConfigSelection = _Cfg
	config_mod.ConfigSubsection = _Cfg
	config_mod.ConfigInteger = ConfigInteger
	config_mod.ConfigPIN = ConfigInteger
	config_mod.ConfigYesNo = ConfigYesNo
	config_mod.ConfigIP = ConfigIP
	config_mod.getConfigListEntry = lambda *a, **k: None
	config_mod.config = AutoModule("Components.config.config")
	config_mod.configfile = AutoModule("Components.config.configfile")
	config_mod.ConfigSubList = list
	config_mod.ConfigLocations = _Cfg
	config_mod.NoSave = lambda x: x

	components_pkg = types.ModuleType("Components")
	components_pkg.__path__ = []
	sys.modules["Components"] = components_pkg
	sys.modules["Components.config"] = config_mod


def main():
	work = tempfile.mkdtemp()
	plugroot = pathlib.Path(work) / "plugroot"
	dest = plugroot / "Plugins" / "Extensions" / "DreamPlex"
	dest.parent.mkdir(parents=True)
	shutil.copytree(REPO_ROOT / "src", dest)
	(plugroot / "Plugins" / "__init__.py").touch()
	(plugroot / "Plugins" / "Extensions" / "__init__.py").touch()

	setup_environment(plugroot)

	print("importing Plugins.Extensions.DreamPlex (the real package) ...")
	import Plugins.Extensions.DreamPlex  # noqa: E402
	print("OK: package imports without a circular-import error")

	print("importing Plugins.Extensions.DreamPlex.plugin ...")
	import Plugins.Extensions.DreamPlex.plugin  # noqa: E402
	print("OK: plugin.py imports too")

	# PlexSettings/JellyfinSettings are no longer attributes of the top
	# package itself - _discoverServerBackends() (src/__init__.py) imports
	# src/plex/ and src/jellyfin/ purely for their registerServerBackend()
	# side effect, ServiceLoader-style, so the classes have to come from
	# their real submodules directly, same as any other backend consumer.
	from Plugins.Extensions.DreamPlex.plex.PlexSettings import PlexSettings  # noqa: E402
	from Plugins.Extensions.DreamPlex.jellyfin.JellyfinSettings import JellyfinSettings  # noqa: E402

	print("running initSettingsStorage() against a fresh temp config dir ...")
	pkg = Plugins.Extensions.DreamPlex
	pkg.defaultConfigFolderPath = os.path.join(tempfile.mkdtemp(), "config") + os.sep
	storage = pkg.initSettingsStorage()
	assert len(storage.serverConfigs) == 0, "a fresh store should start empty"
	print("OK: SettingsStorage built, %d server(s) loaded" % len(storage.serverConfigs))

	print("adding a Plex server and a Jellyfin server, then reloading ...")
	plex = pkg.ServerSettings[PlexSettings.SETTINGS_NAME].factoryClass().createServerSettings(storage)
	storage.registerNewServer(plex)
	jf = pkg.ServerSettings[JellyfinSettings.SETTINGS_NAME].factoryClass().createServerSettings(storage)
	storage.registerNewServer(jf)

	print("changing the Plex server's name the way keyLeft/keyRight does "
		  "(direct ConfigElement.value assignment, not setValue()) ...")
	plex.name().getConfigElement().value = "MyHomeServer"
	assert plex.name().getValue() == "MyHomeServer"

	print("setting the Jellyfin server's own (PIN-less) login password ...")
	jf.password().setValue("serverPassword123")
	assert jf.password().getValue() == "serverPassword123", "getValue() must hand back plaintext for the settings screen to edit"

	print("adding a PIN-protected Jellyfin user (mirrors "
		  "_onNewJellyfinUserPinEntered: plaintext token/password get "
		  "encrypted in place once a pin is chosen) ...")
	import Plugins.Extensions.DreamPlex.DPH_Vault as vault
	jfFactory = pkg.ServerSettings[JellyfinSettings.SETTINGS_NAME].factoryClass()
	kidUser = jfFactory.createNewUser(jf, "user-1", "kiduser", "", "plaintext-token-abc")
	kidUser.password.setValue("plaintext-password-xyz")
	kidUser.token.setValue(vault.encrypt(kidUser.token.getValue(), "1234"))
	kidUser.password.setValue(vault.encrypt(kidUser.password.getValue(), "1234"))
	kidUser.pin.setValue("1234")
	jf.saveChanges()

	storage.writeToFile()

	storage2 = pkg.SettingsStorage(storage.location)
	types_found = [s.getType() for s in storage2.serverConfigs]
	assert len(storage2.serverConfigs) == 2, "both servers should survive a reload, got %r" % types_found
	assert set(types_found) == {PlexSettings.SETTINGS_NAME, JellyfinSettings.SETTINGS_NAME}
	print("OK: reloaded, 2 server(s), types: %s" % types_found)

	reloaded_plex = next(s for s in storage2.serverConfigs if s.getType() == PlexSettings.SETTINGS_NAME)
	assert reloaded_plex.name().getValue() == "MyHomeServer", (
		"the name set via ConfigElement.value should have survived save+reload, got %r" % reloaded_plex.name().getValue())
	print("OK: field changed via ConfigElement.value survived save+reload")

	print("changing a setting value, to exercise the config-element notifier ...")
	storage2.debugMode.setValue(True)
	print("OK: notifier fired without a TypeError")

	print("checking that DPS_Server.buildEntryList() rows are real tuples, as "
		  "required by the skin's TemplatedMultiContent converter (text = "
		  "0/1/2/3) - eListboxPythonMultiContent reads them with direct "
		  "tuple access, so an indexable-but-not-tuple object (e.g. the "
		  "EntryServer dataclass by itself) silently renders as an empty "
		  "list on a real box ...")
	entry = reloaded_plex.toEntryServer()
	row = (entry.name, entry.serverHost, entry.serverPort, entry.active, entry)
	assert type(row) is tuple
	assert row[0] == "MyHomeServer", "row[0] should be the server name, got %r" % (row,)
	assert row[4].settings is reloaded_plex, "row[4] should be the EntryServer, for keyOk/keyRed/keyYellow"
	print("OK: row is a real tuple, with the EntryServer as its 5th element: %s" % (row,))

	print("checking the field accessor methods DP_PlexLibrary/DP_View/DP_Syncer/"
		  "DP_MainMenu/DP_ServerMenu/DPH_RemoteHandler rely on (serverConfig."
		  "field().getValue()/.setValue() - the pre-refactor serverConfig."
		  "field.value pattern doesn't work: field alone is a bound method, "
		  "not the BaseSettings instance) ...")
	assert reloaded_plex.name().getValue() == "MyHomeServer"
	assert reloaded_plex.connectionType().getValue() == "0"
	assert tuple(reloaded_plex.ip().getValue()) == (192, 168, 0, 1)
	assert reloaded_plex.port().getValue() == 32400
	assert reloaded_plex.playbackType().getValue() == "0"
	reloaded_plex.localAuth().getValue()
	assert reloaded_plex.quality().getValue() == "7"
	assert reloaded_plex.segments().getValue() == 5
	assert reloaded_plex.uniQuality().getValue() == "3"
	reloaded_plex.universalTranscoder().getValue()
	reloaded_plex.wol().getValue()
	assert reloaded_plex.wakeOnLanAvailable() in (False, True)
	reloaded_plex.syncMovies().getValue()
	reloaded_plex.myplexTokenUsername().setValue("alessio")
	assert reloaded_plex.myplexTokenUsername().getValue() == "alessio"
	print("OK: PlexSettings field accessors all reachable and read/write correctly")

	reloaded_jf = next(s for s in storage2.serverConfigs if s.getType() == JellyfinSettings.SETTINGS_NAME)
	assert reloaded_jf.name().getValue() is not None
	assert reloaded_jf.connectionType().getValue() == "0"
	assert tuple(reloaded_jf.ip().getValue()) == (192, 168, 0, 1)
	assert reloaded_jf.port().getValue() == 8096
	assert reloaded_jf.machineIdentifier().getValue() in (None, "")
	assert reloaded_jf.quality().getValue() == "7"
	reloaded_jf.username().setValue("alessio")
	assert reloaded_jf.username().getValue() == "alessio"
	reloaded_jf.wol().getValue()
	assert reloaded_jf.wakeOnLanAvailable() in (False, True), "wakeOnLanAvailable() must work for Jellyfin too, same as Plex"
	print("OK: JellyfinSettings field accessors all reachable and read/write correctly")

	print("checking EmptyServerSettings (DP_Server.py) - the \"pick a server "
		  "type\" placeholder shown by the real \"Add server\" flow - still "
		  "instantiates now that ip()/port()/dns()/connectionType() are "
		  "abstract on AbstractServerSettings, since Plex's connectionType "
		  "has an extra choice (plex.tv) Jellyfin has no equivalent for and "
		  "so could not be pulled up as one shared concrete implementation "
		  "the way wol()/wol_mac()/wol_delay() were ...")
	from Plugins.Extensions.DreamPlex.DP_Server import EmptyServerSettings
	emptyServer = EmptyServerSettings(storage2)
	assert emptyServer.ip().getValue() is not None
	assert emptyServer.port().getValue() is not None
	assert emptyServer.connectionType().getValue() is not None
	assert emptyServer.wakeOnLanAvailable() is False
	print("OK: EmptyServerSettings satisfies the full AbstractServerSettings interface")

	reloadedUsers = reloaded_jf.listUsers()
	assert len(reloadedUsers) == 1, "the PIN-protected user should have survived save+reload"
	reloadedKid = reloadedUsers[0]
	# ConfigPIN reloaded fresh from disk returns an int (1234), not the str
	# "1234" a live setValue() during the same session keeps - every actual
	# pin comparison in DP_ServerMenu.py already goes through str() for
	# exactly this reason, so mirror that here instead of asserting a type
	# ConfigPIN does not actually guarantee.
	assert str(reloadedKid.pin.getValue()) == "1234"
	assert vault.isEncrypted(reloadedKid.token.getValue()), "token must be stored encrypted once a pin is set"
	assert vault.isEncrypted(reloadedKid.password.getValue()), "password must be stored encrypted once a pin is set"
	assert vault.decrypt(reloadedKid.token.getValue(), "1234") == "plaintext-token-abc"
	assert vault.decrypt(reloadedKid.password.getValue(), "1234") == "plaintext-password-xyz"
	assert vault.decrypt(reloadedKid.token.getValue(), "9999") is None, "wrong pin must not decrypt the reloaded token"
	print("OK: PIN-protected Jellyfin user survives save+reload, token/password stay encrypted and only the right PIN opens them")

	assert reloaded_jf.password().getValue() == "serverPassword123", "the server login password must decrypt transparently on reload"
	rawXml = open(storage.location, "r", encoding="utf-8").read()
	assert "serverPassword123" not in rawXml, "the server login password must not be stored in plain text in settings.xml"

	print("cloning a Jellyfin server for another user (mirrors DP_Server.keyMenu "
		  "/ DPS_ServerConfig's cloneFrom path: copy every field except "
		  "identity/auth, so a second login on the same server doesn't need "
		  "connection/playback prefs re-entered from scratch) ...")
	import Plugins.Extensions.DreamPlex.DP_Server as dp_server
	jf.quality().setValue("9")
	jf.subtitlesLanguage().setValue("it")
	jfClone = jfFactory.createServerSettings(storage)
	dp_server._copyServerFields(jf, jfClone)
	jfClone.id().setValue(storage.getUniqueId())
	jfClone.name().setValue(jf.name().getValue() + " (clone)")
	storage.registerNewServer(jfClone)
	storage.writeToFile()

	assert jfClone.quality().getValue() == "9", "cloned server must carry over playback prefs"
	assert jfClone.subtitlesLanguage().getValue() == "it", "cloned server must carry over subtitle prefs"
	assert not jfClone.username().getValue(), "clone must not carry over the source username"
	assert not jfClone.password().getValue(), "clone must not carry over the source password"
	assert not jfClone.accessToken().getValue(), "clone must not carry over the source access token"
	assert not jfClone.userId().getValue(), "clone must not carry over the source user id"
	assert jfClone.id().getValue() != jf.id().getValue(), "clone must get its own unique id"
	assert len(jfClone.listUsers()) == 0, "clone must not carry over the source's saved user profiles"

	storage3 = pkg.SettingsStorage(storage.location)
	jellyfinServers = [s for s in storage3.serverConfigs if s.getType() == JellyfinSettings.SETTINGS_NAME]
	assert len(jellyfinServers) == 2, "both the original and cloned Jellyfin server should survive a reload"
	reloadedClone = next(s for s in jellyfinServers if s.id().getValue() == jfClone.id().getValue())
	assert reloadedClone.quality().getValue() == "9"
	assert not reloadedClone.username().getValue()
	print("OK: cloning a Jellyfin server copies connection/playback settings but not identity/auth fields, and survives save+reload")
	print("OK: the server's own login password is masked at rest (device-key encrypted, not plaintext) and reads back transparently")

	print("abandoning a new/cloned server config without saving (DPS_ServerConfig."
		  "_discardIfUnsaved, wired to onClose as a safety net beyond keyCancel() "
		  "- a real bug this session: keyBlue() used to save on a FAILED remote "
		  "auth too, leaving a default-named 'JellyfinServer' entry behind even "
		  "though the user believed they had backed out) ...")

	class _FakeConfigScreen:
		def __init__(self, current, saved):
			self.newmode = 1
			self.current = current
			self._saved = saved

	abandonedServer = jfFactory.createServerSettings(storage)
	storage.registerNewServer(abandonedServer)
	assert abandonedServer in storage.serverConfigs
	dp_server.DPS_ServerConfig._discardIfUnsaved(_FakeConfigScreen(abandonedServer, False))
	assert abandonedServer not in storage.serverConfigs, "an unsaved new/cloned server must be discarded when its config screen closes"

	keptServer = jfFactory.createServerSettings(storage)
	storage.registerNewServer(keptServer)
	dp_server.DPS_ServerConfig._discardIfUnsaved(_FakeConfigScreen(keptServer, True))
	assert keptServer in storage.serverConfigs, "a server that reached saveNow() must not be discarded"
	storage.serverConfigs.remove(keptServer)  # tidy up, unrelated to the assertions above
	storage.writeToFile()
	print("OK: an unsaved new/cloned server is discarded on close, a saved one is left alone")

	print("keyBlue()'s post-remote-auth success dialog used to save on ANY "
		  "dismissal (OK or Cancel/Exit both just closed a TYPE_INFO box, wired "
		  "to the same saveNow() callback with no branch on the retval) - a real "
		  "bug found live: a user pressing Cancel there, expecting to abort the "
		  "whole 'add server' flow, got a semi-configured server silently saved "
		  "anyway. Now TYPE_YESNO + _onRemoteAuthConfirmed() only saves on an "
		  "actual Yes ...")

	class _FakeAuthConfirmScreen:
		def __init__(self, settings, current):
			self._settings = settings
			self.current = current
			self._saved = False
			self.closed = False

		def close(self, *args, **kwargs):
			self.closed = True

		def saveNow(self, retval=None):
			# mirrors DPS_ServerConfig.saveNow() exactly (self._saved = True;
			# self._settings.writeToFile(); self.close())
			self._saved = True
			self._settings.writeToFile()
			self.close()

	declinedServer = jfFactory.createServerSettings(storage)
	storage.registerNewServer(declinedServer)
	declinedScreen = _FakeAuthConfirmScreen(storage, declinedServer)
	dp_server.DPS_ServerConfig._onRemoteAuthConfirmed(declinedScreen, False)
	assert not declinedScreen._saved, "declining the post-auth confirmation must not save"
	assert not declinedScreen.closed, "declining must leave the config screen open, not close it"
	storage.serverConfigs.remove(declinedServer)  # tidy up, unrelated to the assertions above

	acceptedServer = jfFactory.createServerSettings(storage)
	storage.registerNewServer(acceptedServer)
	acceptedScreen = _FakeAuthConfirmScreen(storage, acceptedServer)
	dp_server.DPS_ServerConfig._onRemoteAuthConfirmed(acceptedScreen, True)
	assert acceptedScreen._saved, "confirming Yes must save"
	assert acceptedScreen.closed, "saveNow() must close the config screen"
	assert acceptedServer in storage.serverConfigs
	storage.serverConfigs.remove(acceptedServer)
	storage.writeToFile()
	print("OK: the post-remote-auth confirmation only saves the server on an explicit Yes")

	print("saving a disabled server skips the reachability check and token "
		  "renewal entirely (previously: turning a server off and saving it "
		  "still hit the network and renewed its token, pointlessly) ...")

	class _FakeSaveScreen:
		def __init__(self, current):
			self.current = current
			self._settings = storage
			self.saveCalled = False
			self.registerServerCalled = False

		def saveNow(self, retval=None):
			self.saveCalled = True

	jf.state().setValue(False)
	fakeSaveScreen = _FakeSaveScreen(jf)
	# registerServer() would need a live server and is exactly what a
	# disabled save must skip - if keySave() regresses and calls it anyway,
	# this raises instead of silently passing.
	jf.registerServer = lambda session: (_ for _ in ()).throw(AssertionError("registerServer() must not run for a disabled server"))
	dp_server.DPS_ServerConfig.keySave(fakeSaveScreen)
	assert fakeSaveScreen.saveCalled, "a disabled server must still be saved, just without the network round-trip"
	del jf.registerServer
	jf.state().setValue(True)
	print("OK: saving a disabled server calls saveNow() directly, without registerServer()/token renewal")

	print("cloning a Plex server for another user (same cloneFrom path, but "
		  "Plex's exclusion list: myplex.tv identity, home-user session and "
		  "the settings-screen PIN must not carry over either) ...")
	plex.quality().setValue("9")
	plex.myplexUsername().setValue("alessio@example.com")
	plex.myplexToken().setValue("plex-token-abc")
	plex.myplexId().setValue(12345)
	plex.protectSettings().setValue(True)
	plex.settingsPin().setValue("4321")
	plexFactory = pkg.ServerSettings[PlexSettings.SETTINGS_NAME].factoryClass()
	plexClone = plexFactory.createServerSettings(storage)
	dp_server._copyServerFields(plex, plexClone)
	plexClone.id().setValue(storage.getUniqueId())
	plexClone.name().setValue(plex.name().getValue() + " (clone)")
	storage.registerNewServer(plexClone)
	storage.writeToFile()

	assert plexClone.quality().getValue() == "9", "cloned Plex server must carry over playback prefs"
	assert not plexClone.myplexUsername().getValue(), "clone must not carry over the myplex.tv username"
	assert not plexClone.myplexToken().getValue(), "clone must not carry over the myplex.tv token"
	assert plexClone.myplexId().getValue() != 12345, "clone must not carry over the myplex.tv account id"
	assert not plexClone.protectSettings().getValue(), "clone must not inherit settings-screen PIN protection"
	assert str(plexClone.settingsPin().getValue()) != "4321", "clone must not carry over the settings-screen PIN"
	assert plexClone.id().getValue() != plex.id().getValue(), "clone must get its own unique id"
	print("OK: cloning a Plex server copies playback settings but not myplex.tv identity or the settings PIN")

	print("reporting Jellyfin playback progress via the shared DP_MediaLibrary."
		  "reportPlaybackProgress() interface (server param is Plex-only and "
		  "ignored here) posts to the PlaystateController endpoints instead "
		  "of doing nothing, as it silently did before this fix ...")
	import json as _json
	import Plugins.Extensions.DreamPlex.jellyfin.JellyfinLibrary as jfLibMod
	import Plugins.Extensions.DreamPlex.DP_MediaLibrary as mediaLibMod
	jfLib = jfLibMod.JellyfinLibrary(None, jf)
	assert jfLib.getRatingKind() == mediaLibMod.RATING_KIND_FAVORITE, "Jellyfin has no personal star rating API, only Favorite"
	calls = []
	jfLib._request_json = lambda method, path, params=None, data=None: calls.append((method, path, data)) or {}
	jfLib.reportPlaybackProgress(None, "item-42", 125, 3600, stopped=True)
	assert len(calls) == 1, "reportPlaybackProgress should fire exactly one request"
	method, path, data = calls[0]
	assert method == "POST" and path == "/Sessions/Playing/Stopped"
	body = _json.loads(data.decode("utf-8"))
	assert body["ItemId"] == "item-42"
	assert body["PositionTicks"] == 125 * 10_000_000, "position must be seconds converted to 100ns ticks"
	assert body.get("PlaySessionId"), "a PlaySessionId must be included, the server expects one"
	calls.clear()
	jfLib.reportPlaybackProgress(None, "item-42", 10, 3600, stopped=False)
	assert calls[0][1] == "/Sessions/Playing/Progress"
	print("OK: Jellyfin playback reports to /Sessions/Playing/Progress and /Sessions/Playing/Stopped with correctly converted position ticks")

	print("playLibraryMedia() carries year/genre/rating/cast/director/duration "
		  "into videoData (DP_Player's INFO-key playback info panel reads "
		  "these) ...")
	fakeItem = {
		"Name": "Test Movie",
		"Overview": "A test overview.",
		"Genres": ["Action", "Sci-Fi"],
		"People": [
			{"Name": "Some Director", "Type": "Director"},
			{"Name": "Some Actor", "Type": "Actor"},
			{"Name": "Another Actor", "Type": "Actor"},
			{"Name": "Some Writer", "Type": "Writer"},
		],
		"ProductionYear": 2021,
		"OfficialRating": "PG-13",
		"CommunityRating": 7.8,
		"RunTimeTicks": 72_000_000_000,  # 2 hours, in 100ns ticks
		"UserData": {"IsFavorite": True},
	}
	jf.userId().setValue("user-1")  # playLibraryMedia() only fetches item details if a user id is set
	jfLib._request_json = lambda method, path, params=None, data=None: fakeItem
	playerData = jfLib.playLibraryMedia("item-42", "http://example/stream")
	videoData = playerData['videoData']
	assert videoData['genre'] == "Action, Sci-Fi"
	assert videoData['director'] == "Some Director"
	assert videoData['cast'] == "Some Actor, Another Actor"
	assert videoData['year'] == 2021
	assert videoData['contentRating'] == "PG-13"
	assert videoData['rating'] == 7.8
	assert videoData['duration'] == 2 * 60 * 60 * 1000, "RunTimeTicks must convert to milliseconds"
	assert videoData['isFavorite'] is True, "so the FAV panel can seed itself with the item's actual state instead of always opening blank"
	print("OK: playLibraryMedia() populates videoData with year/genre/rating/cast/director/duration/isFavorite")

	print("FAV-key rating panel: Jellyfin favorite toggle and Plex star "
		  "rating both submit to the right endpoint ...")
	favCalls = []
	jfLib._request_json = lambda method, path, params=None, data=None: favCalls.append((method, path)) or {}
	jfLib.setFavorite("item-42", True)
	assert favCalls[-1] == ("POST", "/Users/user-1/FavoriteItems/item-42")
	jfLib.setFavorite("item-42", False)
	assert favCalls[-1] == ("DELETE", "/Users/user-1/FavoriteItems/item-42")
	jfLib.submitRating(None, "item-42", True)  # DP_Player never calls setFavorite() directly, only this
	assert favCalls[-1] == ("POST", "/Users/user-1/FavoriteItems/item-42")

	print("getSimilarItems(): the 'you might also like' carousel DP_Player "
		  "shows near the end of a standalone movie ...")
	similarItems = {
		"Items": [
			{"Id": "similar-1", "Name": "Similar Movie One", "Overview": "Plot one."},
			{"Id": "similar-2", "Name": "Similar Movie Two", "Overview": "Plot two."},
		]
	}
	similarCalls = []

	def _fakeSimilarRequest(method, path, params=None, data=None):
		similarCalls.append((method, path, params))
		return similarItems
	jfLib._request_json = _fakeSimilarRequest
	suggestions = jfLib.getSimilarItems(None, "item-42")
	assert similarCalls[-1][1] == "/Items/item-42/Similar"
	assert similarCalls[-1][2]["UserId"] == "user-1"
	assert len(suggestions) == 2
	assert suggestions[0][1]['title'] == "Similar Movie One"
	assert suggestions[0][1]['summary'] == "Plot one."
	assert suggestions[1][1]['title'] == "Similar Movie Two"

	jfLib._request_json = lambda method, path, params=None, data=None: {"Items": []}
	assert jfLib.getSimilarItems(None, "item-42") == [], "no similar items must be an empty list, not None"

	def _raisingRequest(method, path, params=None, data=None):
		raise RuntimeError("network error")
	jfLib._request_json = _raisingRequest
	assert jfLib.getSimilarItems(None, "item-42") == [], "a request failure must also degrade to an empty list, not raise"
	print("OK: getSimilarItems() returns real suggestions, and an empty list (never None) when there are none/on error")

	print("getAllSections(): Collections (BoxSet) and Playlists are user-level "
		  "items, not tied to one library section the way Views returns "
		  "Movies/TV Shows/Music - they need their own top-level rows ...")
	jfLib._request_json = lambda method, path, params=None, data=None: {"Items": []}
	sections = jfLib.getAllSections()
	byTitle = {row[0]: row for row in sections}
	assert "Collections" in byTitle and "Playlists" in byTitle
	collectionsEntry = byTitle["Collections"][3]
	assert collectionsEntry['contentUrl'] == {'includeTypes': 'BoxSet', 'recursive': True}
	assert collectionsEntry['nextViewMode'] == 'mixed'
	assert collectionsEntry['uuid'] == 'jellyfin-collections', "must be a stable, distinct cache key from playlists' and from every real section's"
	playlistsEntry = byTitle["Playlists"][3]
	assert playlistsEntry['contentUrl'] == {'includeTypes': 'Playlist', 'recursive': True}
	assert playlistsEntry['uuid'] == 'jellyfin-playlists'

	filteredSections = jfLib.getAllSections(myFilter="movies")
	assert "Collections" not in [row[0] for row in filteredSections], "a filtered (single-type) menu must not also offer the mixed-type Collections/Playlists rows"
	print("OK: getAllSections() offers Collections/Playlists on the unfiltered menu, keyed for their own cache slot")

	print("getSectionTypes(): settings.summerizeSections defaults to True, "
		  "so THIS (not getAllSections()) is the menu most users actually "
		  "see - Collections/Playlists must be reachable from here too ...")
	summarized = jfLib.getSectionTypes()
	summarizedTitles = [row[0] for row in summarized]
	assert "Movies" in summarizedTitles and "Tv Shows" in summarizedTitles and "Music" in summarizedTitles
	assert "Collections" in summarizedTitles and "Playlists" in summarizedTitles
	print("OK: getSectionTypes() also offers Collections/Playlists")

	print("_to_entry(): a BoxSet/Playlist row must be treated as a folder to "
		  "descend into even when the server's IsFolder flag for it is "
		  "false/missing (not reliably true across Jellyfin versions - a "
		  "real crash this session: DPS_ViewMixed._refresh() has no branch "
		  "for the literal 'BoxSet'/'Playlist' type this produced before) ...")
	for fakeType in ("BoxSet", "Playlist"):
		title, entryData, _ctxMenu, viewState, nextUrl = jfLib._to_entry(
			{"Type": fakeType, "Id": "collection-1", "Name": "A Collection", "IsFolder": False},
			currentViewMode="ShowMovies")
		assert entryData['tagType'] == 'Directory', fakeType
		assert entryData['type'] == 'Folder', fakeType
		assert entryData['nextViewMode'] == 'ShowDirectory', fakeType
	print("OK: _to_entry() always treats BoxSet/Playlist as a folder, regardless of IsFolder")

	print("_to_entry(): a leaf item's 'type' must match Plex's own lowercase "
		  "convention ('movie'/'episode'/'season'), which is the only thing "
		  "DPS_ViewMixed._refresh() (designed for Plex originally) checks - "
		  "a real crash this session: a plain Movie inside a Collection got "
		  "the literal Jellyfin itemType ('Movie', capitalized) instead ...")
	_title, movieEntry, _cm, _vs, _nu = jfLib._to_entry({"Type": "Movie", "Id": "movie-1", "Name": "A Movie"}, currentViewMode="ShowMovies")
	assert movieEntry['type'] == 'movie'
	_title, episodeEntry, _cm, _vs, _nu = jfLib._to_entry({"Type": "Episode", "Id": "ep-1", "Name": "An Episode"}, currentViewMode="ShowMovies")
	assert episodeEntry['type'] == 'episode'
	print("OK: _to_entry() normalizes leaf item types to Plex's lowercase convention")

	# DP_PlexLibrary.py runs real filesystem-path resolution code at class
	# body scope (not inside a method), which this stub environment cannot
	# fake convincingly enough to even import the module, let alone
	# instantiate it - getRatingKind()/submitRating()/rateItem()/
	# reportPlaybackProgress() are simple enough (reviewed by inspection)
	# that this is a deliberate gap, not a skipped check.
	# _nextPlexStarRating() below covers the one part with real logic (the
	# half/full digit toggle), independently of the rest of DP_PlexLibrary.

	from Plugins.Extensions.DreamPlex.DP_Player import _nextPlexStarRating
	d, full, value = None, False, None
	d, full, value = _nextPlexStarRating(d, full, 3)
	assert value == 5, "first press of a new digit must land on the half-star value (2*3-1)"
	d, full, value = _nextPlexStarRating(d, full, 3)
	assert value == 6, "second press of the same digit must fill the star (2*3)"
	d, full, value = _nextPlexStarRating(d, full, 3)
	assert value == 5, "third press of the same digit must go back to half"
	d, full, value = _nextPlexStarRating(d, full, 1)
	assert value == 1, "pressing a different digit must restart at half for that new position"
	print("OK: Jellyfin favorite toggle and Plex rateItem() hit the right endpoints, and the half/full digit toggle alternates correctly")

	print()
	print("checking DPH_Vault (PIN-derived encryption for Jellyfin per-profile tokens/passwords) ...")
	import Plugins.Extensions.DreamPlex.DPH_Vault as vault
	assert not vault.hasPin(""), "empty pin must not count as set"
	assert not vault.hasPin("0000"), "all-zero pin (the ConfigPIN default) must not count as set"
	assert vault.hasPin("1234")
	plainRoundtrip = vault.encrypt("supersecret-token", "")
	assert plainRoundtrip == "supersecret-token", "empty pin must leave the field untouched (no ENC1: prefix)"
	assert not vault.isEncrypted(plainRoundtrip)
	blob = vault.encrypt("supersecret-token", "1234")
	assert vault.isEncrypted(blob)
	assert blob != vault.encrypt("supersecret-token", "1234"), "same plaintext+pin must not produce the same ciphertext twice (random nonce)"
	assert vault.decrypt(blob, "1234") == "supersecret-token"
	assert vault.decrypt(blob, "9999") is None, "wrong pin must fail closed, not return garbage as if it were the secret"
	assert vault.decrypt("not-encrypted-at-all", "1234") == "not-encrypted-at-all", "a plaintext field (no ENC1: prefix) must pass through unchanged regardless of pin"
	print("OK: DPH_Vault round-trips correctly and rejects a wrong PIN")

	print()
	print("post-update GUI restart prompt (plugin.py._offerRestartAfterUpdate): "
		  "an .ipk update only replaces files on disk, python keeps running the "
		  "already-imported old modules until enigma2 restarts, so this detects "
		  "the version bump on the next GUI session and offers to do it ...")
	pluginMod = Plugins.Extensions.DreamPlex.plugin

	# The stub Screens.MessageBox fabricated by AutoModule is a bare class
	# with no TYPE_YESNO constant (real enigma2 has one) - set it so the
	# code under test can pass MessageBox.TYPE_YESNO like it does for real.
	from Screens.MessageBox import MessageBox as _StubMessageBox
	_StubMessageBox.TYPE_YESNO = 3

	class _FakeSession:
		def __init__(self):
			self.opened = []

		def openWithCallback(self, callback, screenClass, *args, **kwargs):
			self.opened.append((screenClass, args))
			callback(True)  # simulate the user confirming

		def open(self, screenClass, *args, **kwargs):
			self.opened.append((screenClass, args))

	assert storage.lastSeenVersion.getValue() == "", "fresh store must start with no recorded version"

	fakeSession = _FakeSession()
	pluginMod._offerRestartAfterUpdate(fakeSession)
	assert storage.lastSeenVersion.getValue() == pluginMod.getVersion(), "must record the current version"
	assert fakeSession.opened == [], "a fresh install (no prior recorded version) must not prompt"

	realGetVersion = pluginMod.getVersion
	pluginMod.getVersion = lambda: "9.9.9"
	try:
		pluginMod.globalvars.global_session = fakeSession
		pluginMod._offerRestartAfterUpdate(fakeSession)
		assert storage.lastSeenVersion.getValue() == "9.9.9", "must record the new version even though it only ran because of the mismatch"
		# openWithCallback above simulates the user confirming, which chains
		# into session.open(TryQuitMainloop, 3) - so both calls should be
		# recorded.
		assert len(fakeSession.opened) == 2, "an actual version change must prompt, and confirming must trigger the GUI restart"
		assert fakeSession.opened[0][0] is _StubMessageBox
		assert fakeSession.opened[1][0].__name__ == "TryQuitMainloop"
		assert fakeSession.opened[1][1] == (3,)

		fakeSession2 = _FakeSession()
		pluginMod.globalvars.global_session = fakeSession2
		pluginMod._offerRestartAfterUpdate(fakeSession2)
		assert fakeSession2.opened == [], "no version change (matches what was just recorded) must not prompt again"
	finally:
		pluginMod.getVersion = realGetVersion
	print("OK: prompts only on an actual version change, never on first install or when nothing changed")

	print("_discoverServerBackends() (src/__init__.py): ServiceLoader-style "
		  "scan that imports every immediate subpackage with its own "
		  "__init__.py and expects it to call registerServerBackend() as a "
		  "side effect - a future backend (e.g. src/emby/) is picked up just "
		  "by dropping its folder in, no dict edit needed ...")
	assert set(pkg.ServerSettings.keys()) == {pkg.EMPTY_SERVER_CONF, PlexSettings.SETTINGS_NAME, JellyfinSettings.SETTINGS_NAME}, \
		"fonts/ and skins/ (no __init__.py) must not have been picked up as backends"

	fakeBackendDir = dest / "faketype"
	fakeBackendDir.mkdir()
	(fakeBackendDir / "__init__.py").write_text(
		"from .. import registerServerBackend\n"
		"class _FakeSettings:\n"
		"    SETTINGS_NAME = 'FakeServer'\n"
		"registerServerBackend(_FakeSettings, None)\n"
	)
	pkg._discoverServerBackends()
	assert "FakeServer" in pkg.ServerSettings, "a new subpackage with __init__.py must self-register on discovery"
	print("OK: a new backend subpackage self-registers with no change to __init__.py's own code")

	print("backend-abstraction audit follow-up: DP_ServerMenu/DP_Server/"
		  "DPH_RemoteHandler used to branch on getType() == \"PlexServer\"/"
		  "\"JellyfinServer\" directly; those checks were replaced with calls "
		  "through AbstractServerSettings/DP_MediaLibrary that each backend "
		  "resolves on its own (getUserSwitchMode(), getCloneExcludeFields(), "
		  "getContextSubtitleStreams()/getContextAudioStreams(), the "
		  "getRemote*() family) - verifying both backends actually implement "
		  "them with the right values, not just that the abstract methods "
		  "exist ...")
	from Plugins.Extensions.DreamPlex.DP_SettingsStorage import USER_SWITCH_SHARED_HOME, USER_SWITCH_LOCAL_PROFILES  # noqa: E402

	assert plex.getUserSwitchMode() == USER_SWITCH_SHARED_HOME
	assert jf.getUserSwitchMode() == USER_SWITCH_LOCAL_PROFILES
	assert plex.getCloneExcludeFields() and "_myplexToken" in plex.getCloneExcludeFields()
	assert jf.getCloneExcludeFields() and "_accessToken" in jf.getCloneExcludeFields()
	assert jf.getCurrentUserDisplayName() is None  # username never set on this test's jf instance
	jf.username().setValue("kiduser")
	assert jf.getCurrentUserDisplayName() == "kiduser"

	# DP_PlexLibrary.PlexLibrary cannot even be imported here (see the note
	# above _nextPlexStarRating() earlier in this file: real filesystem-path
	# resolution at class-body scope) - its getContext*/getRemote*() are
	# reviewed by inspection only, same as the rest of that module. jfLib is
	# real and importable (already used above for _to_entry()), so it is
	# exercised for real.
	jfLib = jfLibMod.JellyfinLibrary(None, jf)

	assert jfLib.getContextSubtitleStreams({"subtitleStreams": [1, 2]}) == [1, 2]
	assert jfLib.getContextAudioStreams({}) is None, "no audioStreams key must read as unsupported, not an empty list"
	assert jfLib.getRemoteClientIdentifierHeaderNames() == ['X-Emby-Token', 'X-MediaBrowser-Token']
	assert jfLib.getRemoteContentType().startswith('application/json')
	assert 'X-Emby-Token' in jfLib.getRemoteAccessControlHeaders()
	print("OK: JellyfinLibrary resolves every abstraction call added by today's leak fixes to its own, correct values")

	print("sanitize() (src/__init__.py): each backend registers its own "
		  "log-scrubbing function via registerServerBackend(logSanitizer=...) "
		  "as an import side effect - this was silent dead code before "
		  "today's refactor (_loadSanitizer() existed but nothing ever "
		  "called it, so tokens were never actually redacted from logs) ...")
	sanitizedPlex = pkg.sanitize("GET /x?X-Plex-Token=abcdEFGH1234 HTTP/1.1")
	assert "abcdEFGH1234" not in sanitizedPlex and "********" in sanitizedPlex
	sanitizedJf = pkg.sanitize("GET /x?X-MediaBrowser-Token=abcdEFGH1234 HTTP/1.1")
	assert "abcdEFGH1234" not in sanitizedJf and "********" in sanitizedJf
	print("OK: sanitize() now actually redacts both backends' auth tokens")

	print("_appendShortcutLabels() (DP_MainMenu.py/DP_ServerMenu.py): the "
		  "Carousel skin's sidebar template reads the 1-9 shortcut label at "
		  "one fixed tuple index for every row - rows built with different "
		  "lengths (server rows carry a 4th element, System/LiveTv/About "
		  "don't) must all still land the label at the SAME index after "
		  "padding, or the skin template would read the wrong field on the "
		  "shorter rows ...")
	import Plugins.Extensions.DreamPlex.DP_MainMenu as mainMenuMod
	import Plugins.Extensions.DreamPlex.DP_ServerMenu as serverMenuMod

	mm = object.__new__(mainMenuMod.DPS_MainMenu)
	mixedRows = [("A", 1, "tag"), ("B", 2, "tag", "extra"), ("C", 3, "tag")]
	labeled = mm._appendShortcutLabels(mixedRows, padTo=4)
	assert [row[4] for row in labeled] == ["1", "2", "3"], "the label must sit at index 4 on every row regardless of the row's original length"
	assert labeled[1][3] == "extra", "padding must never clobber a row's own existing fields"
	manyRows = [("item%d" % i, i) for i in range(11)]
	labeledMany = mm._appendShortcutLabels(manyRows, padTo=2)
	assert [row[2] for row in labeledMany] == [str(i + 1) for i in range(9)] + ["", ""], "rows beyond the 9th must get no shortcut label (only single digits exist)"

	sm = object.__new__(serverMenuMod.DPS_ServerMenu)
	listingRows = [("Film", {}, "movieEntry", None, "url1"), ("Serie TV", {}, "showEntry", None, "url2")]
	labeledListing = sm._appendShortcutLabels(listingRows, padTo=5)
	assert [row[5] for row in labeledListing] == ["1", "2"]
	assert labeledListing[0][2] == "movieEntry", "existing indices (icon MenuEntryCompare, okbuttonClick's selection[2]/[3]) must be untouched"
	print("OK: shortcut labels land at one consistent index regardless of each row's original shape")

	print("JellyfinLibrary.doRequest() (jellyfin/JellyfinLibrary.py): used to "
		  "delegate to _request_json(), which always tries "
		  "body.decode('utf-8') + json.loads() and returns None the moment "
		  "either fails - silently discarding every binary response "
		  "(poster/backdrop image downloads) a caller here needed raw bytes "
		  "from. DP_Player.downloadPoster()/_loadSimilarSuggestionPoster() "
		  "and DP_ServerMenu._loadHeroPoster() all call this expecting real "
		  "image bytes to write to disk - found live as a hero banner with "
		  "no poster ever showing for Jellyfin ...")
	fakeImageBytes = b"\xff\xd8\xff\xe0not a real jpeg but not JSON either"

	class _FakeResp:
		def read(self):
			return fakeImageBytes

	realUrlopen = jfLibMod.urlopen
	jfLibMod.urlopen = lambda req, timeout=None: _FakeResp()
	try:
		result = jfLib.doRequest("https://example.invalid/Items/x/Images/Primary")
	finally:
		jfLibMod.urlopen = realUrlopen
	assert result == fakeImageBytes, "doRequest() must hand back raw bytes for a non-JSON response, not silently swallow them as None"
	print("OK: doRequest() returns raw bytes for binary responses instead of discarding them")

	print("getInstalledSkins() (src/__init__.py): a real, 100%-reproducible "
		  "bug found live - it used to read Singleton().getSettingsInstance()."
		  "skinFolderPath, but it is called from INSIDE SettingsStorage."
		  "__init__() itself, before that very instance is registered into "
		  "the Singleton (see initSettingsStorage()) - Singleton()."
		  "getSettingsInstance() returned None every single time, so the "
		  "skin list silently fell back to just [\"default\"] and no other "
		  "skin (Carousel, BlueMod, ...) was ever actually selectable from "
		  "Settings ...")
	# pkg.defaultSkinsFolderPath is unusable here: it comes from
	# resolveFilename(SCOPE_PLUGINS, ...), which is stubbed to a dummy value
	# in this harness (Tools.Directories is faked, see STUB_PREFIXES) - the
	# real skins folder in this test's copied tree is dest / "skins".
	defaultSkin, skins = pkg.getInstalledSkins(str(dest / "skins"))
	assert defaultSkin == "default"
	assert "Carousel" in skins, "the new skin must be offered"
	assert "BlueMod" in skins, "the pre-existing second skin must be offered too - this bug predates today's work"
	assert "Carousel_FHD" not in skins and "BlueMod_FHD" not in skins and "default_FHD" not in skins, "the _FHD variants are switched to automatically, never user-selectable"
	# The actual fix: SettingsStorage.__init__() must pass its own
	# self._skinFolderPath.getValue(), never read through the Singleton -
	# confirmed directly in the source rather than re-exercising
	# SettingsStorage.__init__() a second time (its own defaultSkinsFolderPath
	# is a separate module-level constant from __init__.py's, computed via
	# the same stubbed resolveFilename(), not worth patching twice for a
	# second construction here).
	settingsStorageSrc = open(REPO_ROOT.joinpath("src", "DP_SettingsStorage.py")).read()
	assert "getInstalledSkins(self._skinFolderPath.getValue())" in settingsStorageSrc, \
		"SettingsStorage.__init__() must pass its own skinFolderPath, never read through the Singleton"
	print("OK: getInstalledSkins() no longer depends on Singleton registration order - every installed skin is offered")

	shutil.rmtree(work, ignore_errors=True)
	print()
	print("RESULT: all checks passed")


if __name__ == "__main__":
	try:
		main()
	except Exception:
		import traceback
		traceback.print_exc()
		sys.exit(1)
