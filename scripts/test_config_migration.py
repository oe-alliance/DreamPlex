# -*- coding: utf-8 -*-
"""End-to-end test of the configuration migration, with enigma2 simulated.

Builds a configuration in the pre-3.1 layout (enigma2 settings plus the
homeUsers and mountMappings files), migrates it and reloads the result with
the real SettingsStorage, checking that the values arrive where they should.

The enigma2 modules are stubbed, so this runs on a development machine
without a box. Usage: python3 scripts/test_config_migration.py
"""
import io
import os
import sys
import types
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------
# enigma2 stubs
# --------------------------------------------------------------------------


class _Cfg:
	def __init__(self, default=None):
		self.default = default
		self.value = default
		self.saved_value = None

	def getValue(self):
		return self.value

	def setValue(self, v):
		self.value = v

	def tostring(self, v):
		return "" if v is None else str(v)

	def fromstring(self, s):
		return s

	def addNotifier(self, fn, initial_call=True, immediate_feedback=True):
		pass

	def removeNotifier(self, fn):
		pass


class ConfigText(_Cfg):
	def __init__(self, default="", **kw):
		_Cfg.__init__(self, default)


class ConfigDirectory(ConfigText):
	pass


class ConfigPassword(ConfigText):
	pass


class ConfigInteger(_Cfg):
	def __init__(self, default=0, limits=None):
		_Cfg.__init__(self, default)

	def fromstring(self, s):
		try:
			return int(s)
		except (TypeError, ValueError):
			return self.default


class ConfigPIN(ConfigInteger):
	def __init__(self, default=0, **kw):
		ConfigInteger.__init__(self, default)


class ConfigYesNo(_Cfg):
	def __init__(self, default=False):
		_Cfg.__init__(self, default)

	def tostring(self, v):
		return "true" if v else "false"

	def fromstring(self, s):
		return str(s).lower() in ("true", "1", "yes")


class ConfigSelection(_Cfg):
	def __init__(self, default=None, choices=None):
		_Cfg.__init__(self, default)


class ConfigIP(_Cfg):
	def __init__(self, default=None):
		_Cfg.__init__(self, default or [0, 0, 0, 0])

	def tostring(self, v):
		return ".".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)

	def fromstring(self, s):
		try:
			return [int(x) for x in str(s).split(".")]
		except Exception:
			return self.default


class ConfigSubsection(_Cfg):
	pass


class ConfigElement(_Cfg):
	pass


def _module(name, **attrs):
	m = types.ModuleType(name)
	for k, v in attrs.items():
		setattr(m, k, v)
	sys.modules[name] = m
	return m


_module("Components")
_module("Components.config", getConfigListEntry=lambda *a, **k: None, ConfigElement=ConfigElement, ConfigYesNo=ConfigYesNo,
		ConfigDirectory=ConfigDirectory, ConfigText=ConfigText, ConfigSelection=ConfigSelection,
		ConfigSubsection=ConfigSubsection, ConfigInteger=ConfigInteger,
		ConfigPassword=ConfigPassword, ConfigPIN=ConfigPIN, ConfigIP=ConfigIP)
_module("Tools")
_module("Tools.Directories", resolveFilename=lambda *a, **k: "/usr/lib/enigma2/python/Plugins/Extensions/DreamPlex/",
		SCOPE_PLUGINS=0, SCOPE_SKIN=1, SCOPE_CURRENT_SKIN=2, SCOPE_LANGUAGE=3)

# --------------------------------------------------------------------------
# fake package hosting the real modules under test
# --------------------------------------------------------------------------
pkg = types.ModuleType("dp")
pkg.__path__ = [os.path.join(ROOT, "src")]
sys.modules["dp"] = pkg

common = types.ModuleType("dp.__common__")
common.printl2 = lambda *a, **k: None


def getXmlContent(location):
	try:
		return ET.parse(location).getroot()
	except Exception:
		return None


common.getXmlContent = getXmlContent
common.testMediaServerConnectivity = lambda ip, port: True
common.testInetConnectivity = lambda *a, **k: True


class EntryServer:
	pass


class DiscoveredServer:
	def __init__(self, **kw):
		self.__dict__.update(kw)


common.EntryServer = EntryServer
common.DiscoveredServer = DiscoveredServer
common.getBoxInformation = lambda: "TestBox"
common.getVersion = lambda: "3.1.0"
common.getUUID = lambda: "test-uuid"
common.indentXml = lambda elem, level=0, more_sibs=False: elem
sys.modules["dp.__common__"] = common

init = types.ModuleType("dp.__init__")
init._ = lambda s: s
init.getInstalledSkins = lambda skinFolderPath=None: ("default", [("default", "default")])
init.ServerSettings = {}
init.AbstractServerSettingsFactory = object
init.Singleton = object
sys.modules["dp.__init__"] = init

medialib = types.ModuleType("dp.DP_MediaLibrary")


class DP_MediaLibrary:
	pass


medialib.DP_MediaLibrary = DP_MediaLibrary
sys.modules["dp.DP_MediaLibrary"] = medialib


class ServerSettingsData:
	def __init__(self, name=None, factoryClass=None):
		self.name = name
		self.factoryClass = factoryClass


# "from . import X" looks the attributes up on the package module
pkg.ServerSettingsData = ServerSettingsData
pkg.DP_MediaLibrary = DP_MediaLibrary
pkg.AbstractServerSettingsFactory = object
pkg.Singleton = object
pkg.getInstalledSkins = lambda skinFolderPath=None: ("default", [("default", "default")])
pkg.ServerSettings = {}
pkg._ = lambda s: s


def load(modname, filename):
	src = io.open(os.path.join(ROOT, "src", filename), encoding="utf-8").read()
	m = types.ModuleType(modname)
	m.__package__ = "dp"
	m.__name__ = modname
	sys.modules[modname] = m
	exec(compile(src, filename, "exec"), m.__dict__)
	return m


storage = load("dp.DP_SettingsStorage", "DP_SettingsStorage.py")
init.ServerSettingsData = getattr(storage, "ServerSettingsData", None)
migration = load("dp.DPH_ConfigMigration", "DPH_ConfigMigration.py")

# --------------------------------------------------------------------------
# configuration in the OLD layout
# --------------------------------------------------------------------------
work = tempfile.mkdtemp()
cfg = os.path.join(work, "config")
os.makedirs(cfg)

legacy_settings = os.path.join(work, "settings")
io.open(legacy_settings, "w").write("""\
config.misc.something=1
config.plugins.dreamplex.debugMode=true
config.plugins.dreamplex.boxName=Salotto
config.plugins.dreamplex.useCache=false
config.plugins.dreamplex.seekTime=10
config.plugins.dreamplex.cachefolderpath=/hdd/dreamplex/cache/
config.plugins.dreamplex.entriescount=2
config.plugins.dreamplex.Entries.0.name=Casa
config.plugins.dreamplex.Entries.0.ip=192.168.1.50
config.plugins.dreamplex.Entries.0.port=32400
config.plugins.dreamplex.Entries.0.state=true
config.plugins.dreamplex.Entries.0.myplexUsername=alessio
config.plugins.dreamplex.Entries.0.myplexToken=SEGRETO123
config.plugins.dreamplex.Entries.0.myplexHomeUsers=true
config.plugins.dreamplex.Entries.0.nasRoot=/volume1
config.plugins.dreamplex.Entries.0.smbUser=nasuser
config.plugins.dreamplex.Entries.1.name=Ufficio
config.plugins.dreamplex.Entries.1.ip=192.168.1.51
config.plugins.dreamplex.Entries.1.port=32401
config.plugins.dreamplex.Entries.1.state=false
""")

io.open(os.path.join(cfg, "homeUsers"), "w").write("""\
<xml>
  <server id="0">
    <user id="11" username="alessio" pin="1234" token="TOKEN_A"/>
    <user id="12" username="ospite" pin="0000" token="TOKEN_B"/>
  </server>
</xml>
""")

io.open(os.path.join(cfg, "mountMappings"), "w").write("""\
<xml>
  <server id="0">
    <mapping id="1" remotePathPart="/volume1/video" localPathPart="/mnt/net/nas/video"/>
  </server>
</xml>
""")

# --------------------------------------------------------------------------
# migration
# --------------------------------------------------------------------------
location = os.path.join(cfg, "settings.xml")
ok = migration.migrate(location, cfg, enigma2Settings=legacy_settings)
print("migration ran        :", ok)
assert ok, "the migration should have found something"

root = ET.parse(location).getroot()
servers = root.findall("server-settings")
print("servers migrated     :", len(servers))
print("global settings      :", len([e for e in root if e.tag != "server-settings"]))

print()
print("--- legacy settings cleanup ---")
remaining = [l for l in io.open(legacy_settings, encoding="utf-8") if l.startswith("config.plugins.dreamplex.")]
print("dreamplex lines left in the legacy settings file:", len(remaining))
bad_cleanup = len(remaining) != 0
print("  %-30s %-22s %s" % ("legacy keys removed", str(len(remaining)), "OK" if not bad_cleanup else "EXPECTED 0"))
kept = io.open(legacy_settings, encoding="utf-8").read()
assert "config.misc.something=1" in kept, "unrelated enigma2 settings must survive the cleanup"
print("  %-30s %-22s %s" % ("unrelated settings kept", "config.misc.something", "OK"))

print()
print("--- migration does not re-run once settings.xml exists ---")
mtime_before = os.path.getmtime(location)
ran_again = migration.migrate(location, cfg, enigma2Settings=legacy_settings)
print("  %-30s %-22s %s" % ("second migrate() call", str(ran_again), "OK" if not ran_again else "EXPECTED False"))
bad_second_run = ran_again or os.path.getmtime(location) != mtime_before


def field(elem, name):
	f = elem.find(name)
	return f.text if f is not None else None


print()
print("--- value checks ---")
checks = [
	("global boxName", field(root, "boxName"), "Salotto"),
	("global useCache", field(root, "useCache"), "false"),
	("cacheFolderPath renamed", field(root, "cacheFolderPath"), "/hdd/dreamplex/cache/"),
	("server 0 name", field(servers[0], "name"), "Casa"),
	("server 0 ip", field(servers[0], "ip"), "192.168.1.50"),
	("server 0 token", field(servers[0], "myplexToken"), "SEGRETO123"),
	("server 0 nasRoot preserved", field(servers[0], "nasRoot"), "/volume1"),
	("server 1 name", field(servers[1], "name"), "Ufficio"),
	("server 1 port", field(servers[1], "port"), "32401"),
	("server type", servers[0].get("server-type"), "PlexServer"),
]
users = servers[0].findall("user")
mappings = servers[0].findall("mapping")
checks += [
	("users migrated", str(len(users)), "2"),
	("user 0 pin", field(users[0], "pin"), "1234"),
	("user 1 token", field(users[1], "token"), "TOKEN_B"),
	("mappings migrated", str(len(mappings)), "1"),
	("mapping remotePath", field(mappings[0], "remotePath"), "/volume1/video"),
	("mapping localPath", field(mappings[0], "localPath"), "/mnt/net/nas/video"),
	("entriescount dropped", str(field(root, "entriescount")), "None"),
]

bad = 0
bad += 1 if bad_cleanup else 0
bad += 1 if bad_second_run else 0
for label, got, want in checks:
	ok = got == want
	bad += 0 if ok else 1
	print("  %-30s %-22s %s" % (label, repr(got), "OK" if ok else "EXPECTED %r" % want))


# --------------------------------------------------------------------------
# reload with the real SettingsStorage
# --------------------------------------------------------------------------
print()
print("--- reload with SettingsStorage ---")

plexpkg = types.ModuleType("dp.plex")
plexpkg.__path__ = [os.path.join(ROOT, "src", "plex")]
sys.modules["dp.plex"] = plexpkg

plexlib = types.ModuleType("dp.plex.DP_PlexLibrary")
class PlexLibrary:
	def __init__(self, *a, **k):
		pass
plexlib.PlexLibrary = PlexLibrary
sys.modules["dp.plex.DP_PlexLibrary"] = plexlib

pkg.AbstractServerSettingsFactory = storage.AbstractServerSettingsFactory

def load_sub(modname, subdir, filename, package):
	src = io.open(os.path.join(ROOT, "src", subdir, filename), encoding="utf-8").read()
	m = types.ModuleType(modname)
	m.__package__ = package
	m.__name__ = modname
	sys.modules[modname] = m
	exec(compile(src, filename, "exec"), m.__dict__)
	return m

plexsettings = load_sub("dp.plex.PlexSettings", "plex", "PlexSettings.py", "dp.plex")
PlexSettings = plexsettings.PlexSettings

class _SSD:
	def __init__(self, name, factoryClass):
		self.name = name
		self.factoryClass = factoryClass

registry = {PlexSettings.SETTINGS_NAME: _SSD(PlexSettings.SETTINGS_NAME, plexsettings.PlexSettingsFactory)}
storage.ServerSettings = registry
pkg.ServerSettings = registry

st = storage.SettingsStorage(location)
print("  storage built without errors")
print("  servers loaded               :", len(st.serverConfigs))

s0 = st.serverConfigs[0]
reloaded = [
	("boxName", st.boxName.getValue(), "Salotto"),
	("useCache", st.useCache.getValue(), False),
	("server 0 name", s0._name.getValue(), "Casa"),
	("server 0 port", s0._port.getValue(), 32400),
	("server 0 token", s0._myplexToken.getValue(), "SEGRETO123"),
	("server 1 name", st.serverConfigs[1]._name.getValue(), "Ufficio"),
]
for label, got, want in reloaded:
	ok = got == want
	bad += 0 if ok else 1
	print("  %-30s %-22s %s" % (label, repr(got), "OK" if ok else "EXPECTED %r" % want))

# writing a new value -> must persist
st.boxName.setValue("Camera")
st.writeToFile()
st2 = storage.SettingsStorage(location)
got = st2.boxName.getValue()
ok = got == "Camera"
bad += 0 if ok else 1
print("  %-30s %-22s %s" % ("value rewritten and reread", repr(got), "OK" if ok else "EXPECTED 'Camera'"))

print()
print("RESULT:", "all checks passed" if bad == 0 else "%d FAILED" % bad)
sys.exit(1 if bad else 0)
