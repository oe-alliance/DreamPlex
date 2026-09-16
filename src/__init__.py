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
from __future__ import annotations
import gettext
from dataclasses import dataclass
# ===============================================================================
# IMPORT
# ===============================================================================
from os import environ, listdir
from os.path import isdir, join as path_join, isfile, dirname as path_dirname
from xml.etree.ElementTree import Element, ElementTree
from typing import Type, Callable, List

from Components.Language import language
from Components.config import ConfigSelection
from Tools.Directories import resolveFilename, SCOPE_PLUGINS, SCOPE_SKIN, SCOPE_CURRENT_SKIN, SCOPE_LANGUAGE
from .DPH_Singleton import Singleton
from .DP_SettingsStorage import SettingsStorage, AbstractSettings, AbstractServerSettings, AbstractServerSettingsFactory
from .DP_ViewFactory import getViews
from .DPH_ConfigMigration import migrate
from .__common__ import getVersion, registerPlexFonts, loadSkinParams, loadMainSkin, checkPlexEnvironment, \
	checkDirectory, \
	getBoxInformation, printl2 as printl, getXmlContent, getBoxResolution, getSkinFolder, setSkinFolder, \
	getSkinResolution
def _(txt):
	#printl("", "__init__::_(txt)", "S")

	if len(txt) == 0:
		return ""
	text = gettext.dgettext("DreamPlex", txt)
	if text == txt:
		text = gettext.gettext(txt)

	printl("text = " + str(text), "__init__::_(txt)", "D")

	#printl("", "__init__::_(txt)", "C")
	return text

# _() has to be defined above this point: backend subpackages (src/plex/,
# src/jellyfin/, ...) are imported as part of this module's own execution
# (see _discoverServerBackends() below) and both do "from ..__init__ import
# _" at their own module level. Defining it further down - where it used to
# sit, next to sanitize() - left it missing from this module's namespace at
# the moment those imports run, a circular import that failed with "cannot
# import name '_' from partially initialized module".

#===============================================================================
#
#===============================================================================
version = getVersion()
source = "ipk"  # other option is "ipk"

defaultPluginFolderPath = resolveFilename(SCOPE_PLUGINS, "Extensions/DreamPlex/")
defaultSkinsFolderPath = resolveFilename(SCOPE_PLUGINS, "Extensions/DreamPlex/skins")
defaultLogFolderPath = "/tmp/"
defaultCacheFolderPath = "/hdd/dreamplex/cache/"
defaultMediaFolderPath = "/hdd/dreamplex/media/"
defaultPlayerTempPath = "/hdd/dreamplex/"
defaultConfigFolderPath = "/hdd/dreamplex/config/"

# Single file holding the whole configuration since 3.1: global settings,
# servers, users and path mappings. Before that they were spread across the
# enigma2 settings and the homeUsers / mountMappings files.
SETTINGS_FILE_NAME = "settings.xml"

EMPTY_SERVER_CONF = "EmptyServerConf"

# skin data
defaultSkin = "original"
skins = []
sanitizer: List[Callable[[str, List[int], bool], str]] = []


@dataclass
class ServerSettingsData:
	name: str
	factoryClass: Type[AbstractServerSettingsFactory] | None

ServerSettings: dict[str, ServerSettingsData] = {
	EMPTY_SERVER_CONF: ServerSettingsData(name = "EmptyServerConf", factoryClass = None),
}


def registerServerBackend(settingsClass: Type[AbstractServerSettings], factoryClass: Type[AbstractServerSettingsFactory], logSanitizer: Callable[[str, List[int], bool], str] = None) -> None:
	"""
	ServiceLoader-style self-registration hook: a backend subpackage (e.g.
	src/plex/, src/jellyfin/) calls this from its own __init__.py, as an
	import side effect, instead of this module hardcoding one ServerSettings
	entry per backend. See _discoverServerBackends() below, which is what
	imports those subpackages in the first place.

	`logSanitizer`, if given, is that backend's own log-scrubbing function
	(e.g. redacting its auth token from a logged URL/header) - appended to
	the module-level `sanitizer` list the same way sanitize() already
	expects, ahead of the generic _defaultSanitizer fallback appended once,
	after every import, near the bottom of this module.
	"""
	name = settingsClass.SETTINGS_NAME
	printl("registered server backend: " + name, "__init__::registerServerBackend", "I")
	ServerSettings[name] = ServerSettingsData(name=name, factoryClass=factoryClass)
	if logSanitizer is not None:
		sanitizer.append(logSanitizer)


def _discoverServerBackends() -> None:
	"""
	Imports every immediate subpackage of this plugin that declares itself
	a real Python package (i.e. has its own __init__.py) - each one is
	expected to call registerServerBackend() while it does, the way
	src/plex/__init__.py and src/jellyfin/__init__.py do. A future backend
	(e.g. src/emby/) needs no change here at all: dropping its folder in is
	enough - this is the same idea as Java's ServiceLoader, without needing
	packaging/entry_points for what is a single self-contained plugin.
	Non-package subfolders (fonts/, skins/, __pycache__/) are silently
	skipped, since they have no __init__.py to satisfy this check.
	"""
	import importlib
	packageDir = path_dirname(__file__)
	for name in sorted(listdir(packageDir)):
		if not isdir(path_join(packageDir, name)):
			continue
		if not isfile(path_join(packageDir, name, "__init__.py")):
			continue
		try:
			importlib.import_module("." + name, package=__name__)
		except Exception as e:
			printl("could not load server backend '%s': %s" % (name, str(e)), "__init__::_discoverServerBackends", "W")


_discoverServerBackends()

#===============================================================================
#
#===============================================================================


def initBoxInformation():
	printl("", "__init__::getBoxInformation", "S")

	boxInfo = getBoxInformation()
	printl("=== BOX INFORMATION ===", "__init__::getBoxInformation", "I")
	printl("Box: " + str(boxInfo), "__init__::getBoxInformation", "I")

	printl("", "__init__::getBoxInformation", "C")

#===============================================================================
#
#===============================================================================


def printGlobalSettings():
	printl("", "__init__::initGlobalSettings", "S")

	printl("=== VERSION ===", "__init__::getBoxInformation", "I")
	printl("current Version : " + str(version), "__init__::initGlobalSettings", "I")

	settings: SettingsStorage = Singleton().getSettingsInstance()

	printl("=== GLOBAL SETTINGS ===", "__init__::getBoxInformation", "I")
	printl("debugMode: " + str(settings.debugMode.getValue()), "__init__::initGlobalSettings", "I")
	printl("writeDebugFile: " + str(settings.writeDebugFile.getValue()), "__init__::initGlobalSettings", "I")
	printl("boxName: " + str(settings.boxName.getValue()), "__init__::initGlobalSettings", "I")
	printl("pluginfolderpath: " + str(settings.pluginFolderPath.getValue()), "__init__::initGlobalSettings", "I")
	printl("logfolderpath: " + str(settings.logFolderPath.getValue()), "__init__::initGlobalSettings", "I")
	printl("mediafolderpath: " + str(settings.mediaFolderPath.getValue()), "__init__::initGlobalSettings", "I")
	printl("cachefolderpath: " + str(settings.cacheFolderPath.getValue()), "__init__::initGlobalSettings", "I")
	printl("playerTempPath: " + str(settings.playerTempPath.getValue()), "__init__::initGlobalSettings", "I")
	printl("showInMainMenu: " + str(settings.showInMainMenu.getValue()), "__init__::initGlobalSettings", "I")
	printl("showFilter: " + str(settings.showFilter.getValue()), "__init__::initGlobalSettings", "I")
	printl("autoLanguage: " + str(settings.autoLanguage.getValue()), "__init__::initGlobalSettings", "I")
	printl("stopLiveTvOnStartup: " + str(settings.stopLiveTvOnStartup.getValue()), "__init__::initGlobalSettings", "I")
	printl("playTheme: " + str(settings.playTheme.getValue()), "__init__::initGlobalSettings", "I")
	printl("fastScroll: " + str(settings.fastScroll.getValue()), "__init__::initGlobalSettings", "I")
	printl("summerizeSections: " + str(settings.summerizeSections.getValue()), "__init__::initGlobalSettings", "I")
	printl("summerizeServers: " + str(settings.summerizeServers.getValue()), "__init__::initGlobalSettings", "I")
	printl("useCache: " + str(settings.useCache.getValue()), "__init__::initGlobalSettings", "I")
	printl("usePicCache: " + str(settings.usePicCache.getValue()), "__init__::initGlobalSettings", "I")

	printl("", "__init__::initPlexSettings", "C")

#===============================================================================
#
#===============================================================================


def registerSkinParamsInstance():
	printl("", "__init__::registerSkinParamsInstance", "S")

	settings: SettingsStorage = Singleton().getSettingsInstance()
	boxResolution = str(getBoxResolution())
	skinName = str(settings.skinName.getValue())
	printl("current skin: " + skinName, "__common__::registerSkinParamsInstance", "S")

	# Every skin switches automatically between its HD/FHD variant on an FHD
	# box - checking that a "<skin>_FHD" folder actually exists (not a
	# hardcoded skinName == "default" or "BlueMod" list, which silently left
	# every skin added since - Carousel included - stuck on its HD layout on
	# an FHD box, squeezed into the top-left corner of the screen instead of
	# scaled to fill it) is what makes this apply to a new skin with no code
	# change here, the same way getInstalledSkins() discovers it.
	if boxResolution == "FHD" and isdir(path_join(settings.skinFolderPath.getValue(), "%s_FHD" % skinName)):
		skinName = "%s_FHD" % skinName

	skinfolder = path_join(settings.skinFolderPath.getValue(), skinName)

	setSkinFolder(currentSkinFolder=skinfolder)
	printl("current skinfolder: " + skinfolder, "__common__::checkSkinResolution", "S")

	configXml = getXmlContent(skinfolder + "/params")
	Singleton().getSkinParamsInstance(configXml)

	printl("", "__init__::registerSkinParamsInstance", "C")

#===============================================================================
#
#===============================================================================


def checkSkinResolution():
	printl("", "__init__::checkSkinResolution", "S")

	boxResolution = str(getBoxResolution())
	printl("boxResolution: " + boxResolution, "__common__::checkSkinResolution", "S")

	skinResolution = str(getSkinResolution())
	printl("skinResolution: " + skinResolution, "__common__::checkSkinResolution", "S")

	if boxResolution == "HD" and skinResolution == "FHD":
		# if there is setup another FHD skin but the box skin is HD we switch automatically to default HD skin to avoid wrong screen size
		# which leads to unconfigurable dreamplex
		skinfolder = "/usr/lib/enigma2/python/Plugins/Extensions/DreamPlex/skins/default"
		printl("switching to default due to mismatch of box and skin resolution!")

		setSkinFolder(currentSkinFolder=skinfolder)
		printl("current skinfolder: " + skinfolder, "__common__::checkSkinResolution", "S")

		configXml = getXmlContent(skinfolder + "/params")
		Singleton().getSkinParamsInstance(configXml)

	printl("", "__init__::checkSkinResolution", "C")

#===============================================================================
#
#===============================================================================


def loadPlexPlugins():
	printl("", "__init__::loadPlexPlugins", "S")

	# we have to load them here because they are not ready though
	from .DP_LibMovies import DP_LibMovies
	from .DP_LibShows import DP_LibShows
	from .DP_LibMusic import DP_LibMusic
	from .DP_LibMixed import DP_LibMixed
	from .__plugin__ import registerPlugin, Plugin

	printl("registering ... movies", "__init__::loadPlexPlugins", "D")
	registerPlugin(Plugin(pid="movies", name=_("Movies"), start=DP_LibMovies, where=Plugin.MENU_MOVIES))

	printl("registering ... tvshows", "__init__::loadPlexPlugins", "D")
	registerPlugin(Plugin(pid="tvshows", name=_("TV Shows"), start=DP_LibShows, where=Plugin.MENU_TVSHOWS))

	printl("registering ... music", "__init__::loadPlexPlugins", "D")
	registerPlugin(Plugin(pid="music", name=_("Music"), start=DP_LibMusic, where=Plugin.MENU_MUSIC))

	printl("registering ... mixed", "__init__::loadPlexPlugins", "D")
	registerPlugin(Plugin(pid="mixed", name=_("Mixed"), start=DP_LibMixed, where=Plugin.MENU_MIXED))

	#printl("registering ... pictures", "__initgetBoxInformationt__::loadPlexPlugins", "D")
	#registerPlugin(Plugin(pid="tvshows", name=_("Music"), start=DP_LibPictures, where=Plugin.MENU_PICTURES))

	#printl("registering ... channels", "__initgetBoxInformationt__::loadPlexPlugins", "D")
	#registerPlugin(Plugin(pid="tvshows", name=_("Music"), start=DP_LibChannels, where=Plugin.MENU_CHANNELS))

	printl("", "__init__::loadPlexPlugins", "C")


# Backend-specific log-scrubbing functions (redacting a Plex X-Plex-Token,
# a Jellyfin X-MediaBrowser-Token/X-Emby-Authorization DeviceId, ...) are
# registered by each backend's own __init__.py via registerServerBackend()'s
# sanitizer= parameter (see src/plex/__init__.py, src/jellyfin/__init__.py) -
# this module only owns the generic fallback below, applied after every
# backend-specific one has had a chance to redact something more precisely.
def _defaultSanitizer(string: str, steps:List[int], obfuscate: bool) -> str:
	if obfuscate is True:
		string = string[:-steps[0]]
		for i in range(steps[0]):
			string += "*"
	return string


sanitizer.append(_defaultSanitizer)


#===============================================================================
#
#===============================================================================
def localeInit():
	printl("", "__init__::localeInit", "S")

	lang = language.getLanguage()
	environ["LANGUAGE"] = lang[:2]
	gettext.bindtextdomain("enigma2", resolveFilename(SCOPE_LANGUAGE))
	gettext.textdomain("enigma2")
	gettext.bindtextdomain("DreamPlex", "%s%s" % (resolveFilename(SCOPE_PLUGINS), "Extensions/DreamPlex/locale/"))

	printl("", "__init__::localeInit", "C")

#===============================================================================
#
#===============================================================================


def getInstalledSkins(folderpath: str = None) -> tuple[str, list[str]]:
	printl("", "__init__::getInstalledSkins", "S")

	mySkins = []
	myDefaultSkin = "default"

	try:
		# `folderpath` has to be passed in, not read from
		# Singleton().getSettingsInstance().skinFolderPath - this function is
		# called from inside SettingsStorage.__init__() itself (see
		# DP_SettingsStorage.py), before that very instance gets registered
		# into the Singleton. Reading through the Singleton here returned
		# None every single time, so this always silently fell into the
		# except branch below and only ever offered "default" - a real,
		# 100%-reproducible bug, not something the new Carousel skin
		# triggered.
		if folderpath is None:
			folderpath = defaultSkinsFolderPath
		for skin in listdir(folderpath):
			if skin not in ["default_FHD", "BlueMod_FHD", "Carousel_FHD"]:  # we exclude the _FHD variants because we switch between HD and FHD automatically
				# print(("skin: " + str(skin), None, "D"))
				if isdir(path_join(folderpath, skin)):
					mySkins.append(skin)
	except Exception as ex:
		printl("no skin found in Dreamplex", "__init__::getInstalledSkins", "D")
		printl("Exception(" + str(type(ex)) + "): " + str(ex), "__init__::getInstalledSkins", "E")
		mySkins.append(myDefaultSkin)

	#Also check if a real enigma2 skin contains dreamplex screens
	try:
		skinPath = resolveFilename(SCOPE_SKIN)
		printl("__init__:: Current enigma2 skin " + resolveFilename(SCOPE_CURRENT_SKIN), "__init__::getInstalledSkins", "D")

		for skin in listdir(skinPath):
			path = path_join(skinPath, skin)
			if isdir(path):
				xml = path_join(path, "skin_dreamplex.xml")
				if isfile(xml):
					mySkins.append("~" + skin)
	except Exception as ex:
		printl("no skindata in enigma2 skin found", "__init__::getInstalledSkins", "D")
		printl("Exception(" + str(type(ex)) + "): " + str(ex), "__init__::getInstalledSkins", "E")

	printl("Found enigma2 skins \"%s\"" % str(mySkins), "__init__::getInstalledSkins", "D")

	printl("", "__init__::getInstalledSkins", "C")

	return myDefaultSkin, mySkins

#===============================================================================
#
#===============================================================================


def getViewTypesForSettings():
	printl("", "__init__::getViewTypesForSettings", "S")

	settings: SettingsStorage = Singleton().getSettingsInstance()

	# view settings
	viewChoicesForMovies = getViewsByType("movies")
	settings.defaultMovieView.setConfigElement(ConfigSelection(default="0", choices=viewChoicesForMovies))

	viewChoicesForShows = getViewsByType("shows")
	settings.defaultShowView.setConfigElement(ConfigSelection(default="0", choices=viewChoicesForShows))

	viewChoicesForMusic = getViewsByType("music")
	settings.defaultMusicView.setConfigElement(ConfigSelection(default="0", choices=viewChoicesForMusic))

	printl("", "__init__::getViewTypesForSettings", "C")

#===============================================================================
#
#===============================================================================


def getViewsByType(myType):
	printl("", "__init__::getViewsByType", "S")
	views = getViews(myType)

	viewChoices = []
	i = 0
	for view in views:
		viewChoices.append((str(i), str(view[0])))
		i += 1

	printl("", "__init__::getViewsByType", "C")
	return viewChoices

#===============================================================================
#
#===============================================================================


def sanitize(txt: str, steps:int = 4, obfuscate: bool = False):
	res: str = txt
	for s in sanitizer:
		res = s(res, [steps], obfuscate)
	return res

#===============================================================================
# EXECUTE ON STARTUP
#===============================================================================


def initSettingsStorage():
	"""Create the settings store and register it in the singleton.

	Everything downstream reaches the configuration through
	Singleton().getSettingsInstance(), so this has to run before any other
	step of prepareEnvironment().

	On the first run after an upgrade the file does not exist yet: the
	configuration of the previous layout, spread across the enigma2 settings
	and the homeUsers / mountMappings XML files, is converted here. When there
	is nothing to convert an empty document is created and the defaults apply.
	"""
	printl("", "__init__::initSettingsStorage", "S")

	configFolder = defaultConfigFolderPath
	checkDirectory(configFolder)

	location = path_join(configFolder, SETTINGS_FILE_NAME)

	if not isfile(location):
		printl("settings file not found at " + location, "__init__::initSettingsStorage", "I")

		if not migrate(location, configFolder):
			printl("creating an empty settings file", "__init__::initSettingsStorage", "I")
			ElementTree(Element("dreamplex")).write(location, encoding="utf-8", xml_declaration=True)

	settings = SettingsStorage(location)
	Singleton().getSettingsInstance(settings)

	printl("settings loaded from " + location, "__init__::initSettingsStorage", "I")
	printl("", "__init__::initSettingsStorage", "C")

	return settings


def prepareEnvironment():
	# the order here is important
	localeInit()
	# Plugins() (see plugin.py) already creates the settings singleton before
	# Autostart() ever runs, since enigma2 builds the plugin/menu list first.
	# Calling initSettingsStorage() again here unconditionally would re-parse
	# settings.xml a second time for no reason, and - if the config folder's
	# mount was not ready yet on Plugins()'s much earlier call - risks running
	# the legacy-config migration a second time too.
	if Singleton().getSettingsInstance() is None:
		initSettingsStorage()
	initBoxInformation()
	printGlobalSettings()
	registerSkinParamsInstance()
	loadSkinParams()
	checkSkinResolution()
	getViewTypesForSettings()
	checkPlexEnvironment()
	registerPlexFonts()
	loadPlexPlugins()

#===============================================================================
#
#===============================================================================


def startEnvironment():
	# prepareEnvironment() only runs once, at Autostart(reason=0) - i.e.
	# enigma2 boot - so a skin change made in Settings only used to take
	# effect after a full GUI restart, even though this function itself
	# (unlike prepareEnvironment()) already runs on every single plugin
	# entry (see plugin.py's DPS_MainMenu()). Re-resolving the skin folder
	# here too is what makes "exit and reopen the plugin" enough - both
	# calls are idempotent (they just re-set the same globals), so running
	# them twice at boot (once via prepareEnvironment(), once here) is
	# harmless.
	registerSkinParamsInstance()
	loadSkinParams()
	checkSkinResolution()

	# we put load skin here to avoid bootloops if there is something wrong with the skin
	loadMainSkin()
