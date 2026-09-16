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
#===============================================================================
# IMPORT
#===============================================================================
from __future__ import annotations
from typing import Any, TYPE_CHECKING
import sys
import os
import datetime
import shutil
import math
import uuid
import glob
from dataclasses import dataclass

from six import PY2

from enigma import addFont, loadPNG, loadJPG, getDesktop
from skin import loadSkin
from Components.AVSwitch import AVSwitch

# AbstractServerSettings, ServerSettings, ServerSettingsData,
# AbstractServerSettingsFactory and sanitize all live in __init__.py, and
# __init__.py imports THIS module (via DP_SettingsStorage) before defining
# any of them: importing them here at module level is a circular import that
# fails with "cannot import name ... from partially initialized module".
# AbstractServerSettings, ServerSettingsData and AbstractServerSettingsFactory
# are only ever used in annotations, deferred to strings by the future import
# above, so TYPE_CHECKING is enough for them. ServerSettings and sanitize are
# called for real, so each is imported locally where it is used.
if TYPE_CHECKING:
	from . import AbstractServerSettings, ServerSettings, ServerSettingsData, AbstractServerSettingsFactory

from .DPH_Singleton import Singleton

#===============================================================================
# import cProfile
#===============================================================================
try:
	# Python 2.5
	import xml.etree.cElementTree as etree
#printl2("running with cElementTree on Python 2.5+", __name__, "D")
except ImportError:
	try:
		# Python 2.5
		import xml.etree.ElementTree as etree
	#printl2("running with ElementTree on Python 2.5+", __name__, "D")
	except ImportError:
		#printl2("something went wrong during etree import" + str(e), self, "E")
		etree = None
		raise Exception

#===============================================================================
# CONSTANTS
#===============================================================================
version = "3.1.1"
boxResoltion = None
skinAuthors = ""
skinResolution = "HD"
skinCompatibility = "v2"
skinDebugMode = False
skinHighlightedColor = "#e69405"
skinNormalColor = "#ffffff"
skinFolder: str | None = None
g_boxData: tuple[Any, Any, Any, Any] | None = None
screens = []
liveTv = None
g_uuid = None
STARTING_MESSAGE = ">>>>>>>>>>"
CLOSING_MESSAGE = "<<<<<<<<<<"
#===============================================================================
#
#===============================================================================


def printl2(string, parent=None, dmode="U", obfuscate=False, steps=4):
	"""
    @param string:
    @param parent:
    @param dmode: default = "U" undefined
                            "E" shows error
                            "W" shows warning
                            "I" shows important information to have better overview if something really happening or not
                            "D" shows additional debug information for better debugging
                            "S" shows started functions/classes etc.
                            "C" shows closing functions/classes etc.
    @return: none
    """

	# A handful of module-level globals (e.g. DP_Syncer's MediaSyncerInfo) are
	# constructed while their own module is first imported, which can happen
	# before initSettingsStorage() has run - settings do not exist yet. printl
	# is a logging helper: it must never be able to crash the plugin just
	# because it was called too early, so treat "no settings yet" the same as
	# "debug logging is off", which is what happens anyway once they load.
	instance: Singleton = Singleton()
	settings = instance.getSettingsInstance()
	debugMode: bool = settings is not None and settings.debugMode.getValue()

	if debugMode:
		from . import sanitize  # see the note on the TYPE_CHECKING import above
		string = sanitize(string, steps, obfuscate)

		if parent is None:
			out = str(string)
		else:
			classname = str(parent.__class__).rsplit(".", 1)
			if len(classname) == 2:
				classname = classname[1]
				classname = classname.rstrip("\'>")
				classname += "::"
				out = str(classname) + str(sys._getframe(1).f_code.co_name) + " -> " + str(string)
			else:
				out = str(parent) + " -> " + str(string)

		if dmode == "E":
			print("[DreamPlex] " + "E" + "  " + str(out))
			writeToLog(dmode, out)

		elif dmode == "W":
			print("[DreamPlex] " + "W" + "  " + str(out))
			writeToLog(dmode, out)

		elif dmode == "I":
			print("[DreamPlex] " + "I" + "  " + str(out))
			writeToLog(dmode, out)

		elif dmode == "D":
			print("[DreamPlex] " + "D" + "  " + str(out))
			writeToLog(dmode, out)

		elif dmode == "S":
			print("[DreamPlex] " + "S" + "  " + str(out) + STARTING_MESSAGE)
			writeToLog(dmode, out + STARTING_MESSAGE)

		elif dmode == "C":
			print("[DreamPlex] " + "C" + "  " + str(out) + CLOSING_MESSAGE)
			writeToLog(dmode, out + CLOSING_MESSAGE)

		elif dmode == "U":
			print("[DreamPlex] " + "U  specify me!!!!!" + "  " + str(out))
			writeToLog(dmode, out)

		elif dmode == "X":
			print("[DreamPlex] " + "D" + "  " + str(out))
			writeToLog(dmode, out)

		else:
			print("[DreamPlex] " + "OLD CHARACTER CHANGE ME !!!!!" + "  " + str(out))

#===============================================================================
#
#===============================================================================


def getVersion():
	return str(version)

#===============================================================================
#
#===============================================================================


def getSkinAuthors():
	return skinAuthors

#===============================================================================
#
#===============================================================================


def getSkinHighlightedColor():
	return skinHighlightedColor

#===============================================================================
#
#===============================================================================


def getSkinNormalColor():
	return skinNormalColor

#===============================================================================
#
#===============================================================================


def getSkinCompatibility():
	return skinCompatibility

#===============================================================================
#
#===============================================================================


def getSkinDebugMode():
	return skinDebugMode

#===============================================================================
#
#===============================================================================


def getSkinResolution():
	return skinResolution

#===============================================================================
#
#===============================================================================


def revokeCacheFiles():
	printl2("", "__common__::revokeCacheFiles", "S")
	instance: Singleton = Singleton()
	settings = instance.getSettingsInstance()
	cachePath = settings.cacheFolderPath.getValue()

	try:
		os.chdir(cachePath)
		files = glob.glob('*.cache')
		for filename in files:
			os.unlink(filename)

	except Exception as ex:
		printl2("Exception(" + str(type(ex)) + "): " + str(ex), "__common__::revokeCacheFiles", "E")

	# Posters/backdrops (mediaFolderPath) are a separate cache from the
	# listing .cache files above - downloaded once by DP_Syncer/DP_View and
	# never re-checked again once a file with that name exists (see
	# DP_View.showPoster()/showBackdrop(), DP_Syncer.syncThroughMediaLibrary()) -
	# "Delete cache" used to leave them untouched, the only way to force a
	# redownload was deleting them by hand. bootlogo.m1v is left alone - it
	# is not something this plugin downloads or regenerates, so it is not
	# "cache" even though it lives in the same folder.
	try:
		mediaPath = settings.mediaFolderPath.getValue()
		os.chdir(mediaPath)
		for pattern in ('*.jpg', '*.m1v'):
			for filename in glob.glob(pattern):
				if filename == 'bootlogo.m1v':
					continue
				os.unlink(filename)

	except Exception as ex:
		printl2("Exception(" + str(type(ex)) + "): " + str(ex), "__common__::revokeCacheFiles", "E")

	printl2("", "__common__::revokeCacheFiles", "C")

#===============================================================================
#
#===============================================================================


def writeToLog(dmode, out):
	"""
    singleton handler for the log file

    @param dmode: E, W, S, H, A, C, I
    @param out: message string
    @return: none
    """

	instance = Singleton()

	if instance.getSettingsInstance().writeDebugFile.getValue():
		try:
			if instance.getLogFileInstance() == "":
				openLogFile()
				gLogFile = instance.getLogFileInstance()
				gLogFile.truncate()
			else:
				gLogFile = instance.getLogFileInstance()

			now = datetime.datetime.now()
			gLogFile.write("%02d:%02d:%02d.%07d " % (now.hour, now.minute, now.second, now.microsecond) + " >>> " + str(dmode) + " <<<  " + str(out) + "\n")
			gLogFile.flush()

		except Exception as ex:
			instance.getSettingsInstance().writeDebugFile.setValue(False)
			instance.getSettingsInstance().writeToFile()
			printl2("Exception(" + str(type(ex)) + "): " + str(ex), "__common__::writeToLog", "E")

#===============================================================================
#
#===============================================================================


def openLogFile():
	"""
    singleton instance for logfile
    """
	#printl2("", "openLogFile", "S")
	instance: Singleton = Singleton()
	logDir = instance.getSettingsInstance().logFolderPath.getValue()

	try:
		if os.path.exists(logDir + "dreamplex_former.log"):
			os.remove(logDir + "dreamplex_former.log")

		if os.path.exists(logDir + "dreamplex.log"):
			shutil.copy2(logDir + "dreamplex.log", logDir + "dreamplex_former.log")

		instance.getLogFileInstance(open(logDir + "dreamplex.log", "w"))

	except Exception as ex:
		printl2("Exception(" + str(type(ex)) + "): " + str(ex), "openLogFile", "E")

#printl2("", "openLogFile", "C")

#===============================================================================
#
#===============================================================================


def testInetConnectivity(target="https://www.google.com"):
	"""
    test if we get an answer from the specified url

    @param target:
    @return: bool
    """
	printl2("", "__common__::testInetConnectivity", "S")

	try:
		from urllib.request import build_opener
	except Exception:
		from urllib2 import build_opener

	try:
		opener = build_opener()
		page = opener.open(target, timeout=2)
		if page is not None:
			printl2("success, returning TRUE", "__common__::testInetConnectivity", "D")
			printl2("", "__common__::testInetConnectivity", "C")
			return True
		else:
			printl2("failure, returning FALSE", "__common__::testInetConnectivity", "D")
			printl2("", "__common__::testInetConnectivity", "C")
			return False
	except Exception:
		printl2("exception, returning FALSE", "__common__::testInetConnectivity", "D")
		printl2("", "__common__::testInetConnectivity", "C")
		return False

#===============================================================================
#
#===============================================================================


def testMediaServerConnectivity(ip, port):
	"""
    test if the plex server is online on the specified port

    @param ip: e.g. 192.168.0.1
    @param port: e.g. 32400
    @return: bool
    """
	printl2("", "__common__::testMediaServerConnectivity", "S")

	import socket

	sock = socket.socket()

	printl2("IP => " + str(ip), "__common__::testMediaServerConnectivity", "I")
	printl2("PORT => " + str(port), "__common__::testMediaServerConnectivity", "I")

	try:
		sock.settimeout(5)
		sock.connect((ip, port))
		sock.close()

		printl2("", "__common__::testMediaServerConnectivity", "C")
		return True
	except socket.error as e:
		printl2("Strange error creating socket: %s" % e, "__common__::testMediaServerConnectivity", "E")
		sock.close()

		printl2("", "__common__::testMediaServerConnectivity", "C")
		return False


#===============================================================================
#
#===============================================================================
def registerPlexFonts():
	"""
    registers fonts for skins

    @param: none
    @return none
    """
	printl2("", "__common__::registerPlexFonts", "S")

	printl2("adding fonts", "__common__::registerPlexFonts", "D")

	tree = Singleton().getSkinParamsInstance()

	for font in tree.findall('font'):
		path = str(font.get('path'))
		printl2("path: " + str(font.get('path')), "__common__::registerPlexFonts", "D")

		size = int(font.get('size'))
		printl2("size: " + str(font.get('size')), "__common__::registerPlexFonts", "D")

		name = str(font.get('name'))
		printl2("name: " + str(font.get('name')), "__common__::registerPlexFonts", "D")

		addFont(path, name, size, False)
		printl2("added => " + name, "__common__::registerPlexFonts", "D")

	printl2("", "__common__::registerPlexFonts", "C")

#===============================================================================
#
#===============================================================================


def getBoxResolution():
	printl2("", "__common__::getBoxResolution", "S")
	global boxResoltion

	if boxResoltion is None:
		screenwidth = getDesktop(0).size().width()
		printl2("screenwidth => " + str(screenwidth), "__common__::getBoxResolution", "D")

		if screenwidth and screenwidth == 1920:
			boxResoltion = "FHD"
		else:
			boxResoltion = "HD"

	printl2("boxResoltion => " + str(boxResoltion), "__common__::getBoxResolution", "D")

	printl2("", "__common__::getBoxResolution", "C")
	return boxResoltion

#===============================================================================
#
#===============================================================================


def loadSkinParams():
	printl2("", "__common__::loadSkinParams", "S")

	global skinAuthors
	global skinCompatibility
	global skinResolution
	global skinDebugMode
	global skinHighlightedColor
	global skinNormalColor

	tree = Singleton().getSkinParamsInstance()

	for skinParams in tree.findall('skinParams'):
		skinCompatibility = str(skinParams.get('compatibility'))
		skinAuthors = str(skinParams.get('skinner'))
		skinResolution = str(skinParams.get('resolution'))
		skinDebugMode = str(skinParams.get('debugMode'))
		skinHighlightedColor = str(skinParams.get('highlighted'))
		skinNormalColor = str(skinParams.get('normal'))

	printl2("", "__common__::loadSkinParams", "C")

#===============================================================================
#
#===============================================================================


def loadMainSkin():
	"""
    loads the corresponding skin.xml file

    @param: none
    @return none
    """
	printl2("", "__common__::loadMainSkin", "S")

	currentSkin = getSkinFolder() + "/skin.xml"

	loadSkin(currentSkin)

	printl2("", "__common__::loadMainSkin", "C")

#===============================================================================
#
#===============================================================================


def checkPlexEnvironment():
	"""
    checks needed file structure for plex

    @param: none
    @return none
    """
	printl2("", "__common__::checkPlexEnvironment", "S")

	instance: Singleton = Singleton()
	settings = instance.getSettingsInstance()

	playerTempFolder = settings.playerTempPath.getValue()
	logFolder = settings.logFolderPath.getValue()
	mediaFolder = settings.mediaFolderPath.getValue()
	configFolder = settings.configFolderPath.getValue()
	cacheFolder = settings.cacheFolderPath.getValue()
	homeUsersFolder = settings.homeUsersFolderPath.getValue()

	checkDirectory(playerTempFolder)
	checkDirectory(logFolder)
	checkDirectory(mediaFolder)
	checkDirectory(configFolder)
	checkDirectory(cacheFolder)
	checkDirectory(homeUsersFolder)

	printl2("", "__common__::checkPlexEnvironment", "C")

#===============================================================================
#
#===============================================================================


def checkDirectory(directory):
	"""
    checks if dir exists. if not it is added

    @param directory: e.g. /media/hdd/
    @return: none
    """
	printl2("", "__common__::checkDirectory", "S")
	printl2("checking ... " + directory, "__common__::checkDirectory", "D")

	try:
		if not os.path.exists(directory):
			os.makedirs(directory)
			printl2("directory not found ... added", "__common__::checkDirectory", "D")
		else:
			printl2("directory found ... nothing to do", "__common__::checkDirectory", "D")

	except Exception as ex:
		printl2("Exception(" + str(type(ex)) + "): " + str(ex), "__common__::checkDirectory", "E")

	printl2("", "__common__::checkDirectory", "C")

#===============================================================================
#
#===============================================================================


def getBoxInformation():
	"""
    @return: manu, model, arch, version
    """
	printl2("", "__common__::getBoxtype", "S")

	if g_boxData is None:
		setBoxInformation()

	printl2("", "__common__::getBoxtype", "C")
	return g_boxData

#===============================================================================
#
#===============================================================================


def getUUID():
	printl2("", "__common__::getUUID", "S")
	global g_uuid

	if g_uuid is None:
		g_uuid = str(uuid.uuid4())

	printl2("", "__common__::getUUID", "C")
	return str(g_uuid)

#===============================================================================
#
#===============================================================================


def setBoxInformation():
	printl2("", "__common__::_setBoxtype", "C")

	try:
		from Components.SystemInfo import BoxInfo
		manu = BoxInfo.getItem("displaybrand", "unknown")
		oe = BoxInfo.getItem("oe", "unknown")
		arch = BoxInfo.getItem("architecture", "unknown")
		model = BoxInfo.getItem("model", "unknown")
	except ImportError:
		from boxbranding import getMachineBuild
		model = getMachineBuild()
		arch = "unknown"
		oe = "unknown"
		manu = "unknown"

	global g_boxData
	g_boxData = (manu, model, arch, oe)

	printl2("", "__common__::_setBoxtype", "C")

#===========================================================================
#
#===========================================================================


def setSkinFolder(currentSkinFolder):
	printl2("", "__common__::setSkinFolder", "S")

	global skinFolder
	skinFolder = currentSkinFolder

	printl2("", "__common__::setSkinFolder", "C")

#===========================================================================
# there is no / at the end
#===========================================================================


def getSkinFolder() -> str:
	printl2("", "__common__::getSkinFolder", "S")

	printl2("", "__common__::getSkinFolder", "C")
	return skinFolder

#===============================================================================
#
#===============================================================================


def prettyFormatTime(msec):
	printl2("", "__common__::prettyFormatTime", "S")

	seconds = msec / 1000
	hours = seconds // (60 * 60)
	seconds %= (60 * 60)
	minutes = seconds // 60
	seconds %= 60
	hrstr = "hour"
	minstr = "min"
	secstr = "sec"

	if hours != 1:
		hrstr += "s"

	if minutes != 1:
		minstr += "s"

	if seconds != 1:
		secstr += "s"

	if hours > 0:
		printl2("", "__common__::prettyFormatTime", "C")
		return "%i %s %02i %s %02i %s" % (hours, hrstr, minutes, minstr, seconds, secstr)

	elif minutes > 0:
		printl2("", "__common__::prettyFormatTime", "C")
		return "%i %s %02i %s" % (minutes, minstr, seconds, secstr)

	else:
		printl2("", "__common__::prettyFormatTime", "C")
		return "%i %s" % (seconds, secstr)

#===============================================================================
#
#===============================================================================


def formatTime(msec):
	printl2("", "__common__::formatTime", "S")

	seconds = msec / 1000
	hours = seconds // (60 * 60)
	seconds %= (60 * 60)
	minutes = seconds // 60
	seconds %= 60

	if hours > 0:
		printl2("", "__common__::formatTime", "C")
		return "%i:%02i:%02i" % (hours, minutes, seconds)

	elif minutes > 0:
		printl2("", "__common__::formatTime", "C")
		return "%i:%02i" % (minutes, seconds)

	else:
		printl2("", "__common__::formatTime", "C")
		return "%i" % seconds

#===============================================================================
#
#===============================================================================


def getScale():
	printl2("", "__common__::getScale", "S")

	printl2("", "__common__::getScale", "C")
	return AVSwitch().getFramebufferScale()

#===========================================================================
#
#===========================================================================

def checkXmlFile(location):
	printl2("", "__common__::checkXmlFile", "S")

	if not os.path.isfile(location):

		try:
			printl2("xml file not found, generating ...", "__common__::checkXmlFile", "D")
			with open(location, "a") as writefile:
				writefile.write("<xml></xml>")
				printl2("writing xml file done", "__common__::checkXmlFile", "D")

		except IOError:
			printl2("io error writing xml", "__common__::checkXmlFile", "D")

		except Exception as e:
			printl2("unknow error writing xml: " + str(e), "__common__::checkXmlFile", "D")

	else:
		printl2("found xml file, nothing to do", "__common__::checkXmlFile", "D")

	printl2("", "__common__::checkXmlFile", "C")

#===========================================================================
#
#===========================================================================


def getXmlContent(location):
	printl2("", "__common__::getXmlContent", "S")

	checkXmlFile(location)

	xml = open(location).read()
	printl2("xml: " + str(xml), "__common__::getXmlContent", "D")

	tree = None

	try:
		tree = etree.fromstring(xml)
	except Exception as e:
		printl2("something weng wrong during xml parsing" + str(e), __name__, "E")

	printl2("", "__common__::getXmlContent", "C")
	return tree

#===========================================================================
#
#===========================================================================


def writeXmlContent(content, location):
	printl2("", "__common__::writeXmlContent", "S")

	indented = indentXml(content)
	xmlString = etree.tostring(indented)
	fobj = open(location, "wb")
	fobj.write(xmlString)
	fobj.close()
	printl2("xmlString: " + str(xmlString), "__common__::getXmlContent", "C")

	printl2("", "__common__::getXmlContent", "C")

#===========================================================================
#
#===========================================================================


def downloadFileAsync(url, destPath, headers=None, callback=None, errback=None):
	"""Download url to destPath in a background thread, calling callback()
	(or errback(exception)) on the enigma2 main thread once it is done.

	This used to be done with Twisted's downloadPage(), which pulls in
	twisted.web.client and, with it, twisted.internet.reactor. enigma2
	itself is Twisted-based and already has a reactor installed by the time
	any plugin loads: the moment DreamPlex's own import chain reached this
	module, Twisted's lazy default-reactor selection tried to install a
	second one and raised ReactorAlreadyInstalledError, which enigma2's
	plugin loader reported as "Extensions/DreamPlex (reactor already
	installed)" and refused to load the plugin at all - there is no
	recovering from that short of never touching twisted.internet.reactor
	in the first place. There is no reason to depend on Twisted for a plain
	file download, so this uses urllib instead.

	The download itself runs in a worker thread so it does not block the
	main loop; the result is picked up by an eTimer polling every 100 ms,
	since only the main thread may touch enigma2 UI objects. The timer is
	returned and MUST be kept referenced by the caller (e.g. as an instance
	attribute) for as long as the download can still be in flight - nothing
	else keeps it alive, and an unreferenced eTimer can be garbage collected
	before it fires.
	"""
	from urllib.request import urlopen, Request
	import threading
	import shutil
	from enigma import eTimer

	result = {}

	def worker():
		try:
			req = Request(url, headers=headers or {})
			with urlopen(req, timeout=20) as resp, open(destPath, "wb") as out:
				shutil.copyfileobj(resp, out)
			result["ok"] = True
		except Exception as ex:
			result["ok"] = False
			result["error"] = ex

	thread = threading.Thread(target=worker)
	thread.daemon = True
	thread.start()

	timer = eTimer()

	def poll():
		if thread.is_alive():
			return
		timer.stop()
		if result.get("ok"):
			if callback is not None:
				callback()
		elif errback is not None:
			errback(result.get("error"))

	timer.callback.append(poll)
	timer.start(100, False)
	return timer

#===========================================================================
#
#===========================================================================


def indentXml(elem, level=0, more_sibs=False):
	printl2("", "__common__::indentXml", "S")

	i = "\n"
	if level:
		i += (level - 1) * '  '
	num_kids = len(elem)
	if num_kids:
		if not elem.text or not elem.text.strip():
			elem.text = i + "  "
			if level:
				elem.text += '  '
		count = 0
		for kid in elem:
			indentXml(kid, level + 1, count < num_kids - 1)
			count += 1
		if not elem.tail or not elem.tail.strip():
			elem.tail = i
			if more_sibs:
				elem.tail += '  '
	else:
		if level and (not elem.tail or not elem.tail.strip()):
			elem.tail = i
			if more_sibs:
				elem.tail += '  '

	printl2("", "__common__::indentXml", "C")
	return elem

#===========================================================================
#
#===========================================================================


def durationToTime(duration):
	printl2("", "__common__::durationToTime", "S")

	m, s = divmod(int(duration) / 1000, 60)
	h, m = divmod(m, 60)

	printl2("", "__common__::durationToTime", "C")
	return "%d:%02d:%02d" % (h, m, s)

#===========================================================================
#
#===========================================================================


def convertSize(size):
	printl2("", "__common__::convertSize", "S")

	size_name = ("KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
	i = int(math.floor(math.log(size, 1024)))
	p = math.pow(1024, i)
	s = round(size / p, 2)

	if s > 0:
		printl2("", "__common__::convertSize", "C")
		return '%s %s' % (s, size_name[i])
	else:
		printl2("", "__common__::convertSize", "C")
		return '0B'

#===========================================================================
#
#===========================================================================


def loadPicture(filename):
	printl2("", "__common__::loadPicture", "S")
	ptr = None
	if filename is None:
		printl2("", "__common__::loadPicture", "C")
		return ptr

	if filename[-4:] == ".png":
		ptr = loadPNG(filename)
	elif filename[-4:] == ".jpg":
		ptr = loadJPG(filename)
		if not ptr:
			# kind of fallback if filetype is declared wrong
			ptr = loadPNG(filename)
	printl2("filename: " + str(filename), "__common__::loadPicture", "D")
	printl2("", "__common__::loadPicture", "C")
	return ptr

#===========================================================================
#
#===========================================================================


def isValidSize(size):
	printl2("", "__common__::isValidSize", "S")
	valid = False
	result = size / 16
	if size % 16 == 0:
		valid = True

	printl2("", "__common__::isValidSize", "C")
	return valid, result

#===========================================================================
#
#===========================================================================


def saveLiveTv(currentService):
	printl2("", "__common__::saveLiveTv", "S")

	global liveTv

	liveTv = currentService

	printl2("", "__common__::saveLiveTv", "C")

#===========================================================================
#
#===========================================================================


def getLiveTv():
	printl2("", "__common__::restoreLiveTv", "S")

	printl2("liveTv: " + str(liveTv), "__common__::restoreLiveTv", "D")

	printl2("", "__common__::restoreLiveTv", "C")
	return liveTv

#===========================================================================
#
#===========================================================================


def addNewScreen(screen):
	printl2("", "__common__::addNewScreen", "S")

	screens.append(screen)

	printl2("", "__common__::addNewScreen", "C")

#===========================================================================
#
#===========================================================================


def closePlugin(session):
	printl2("", "__common__::closePlugin", "S")

	for screen in screens:
		try:
			screen.close()
		except Exception:
			# TODO check for memory usage if we are really free after close
			# this could take place if the screen was closed already manually
			pass
		finally:
			session.nav.playService(getLiveTv())

	printl2("", "__common__::closePlugin", "C")

#===========================================================================
#
#===========================================================================


def getPlexHeader(g_sessionID, asDict=True):
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

#===========================================================================
#
#===========================================================================


def getUserAgentHeader(asDict=True):
	printl2("", "__common__::getUserAgentHeader", "S")

	if asDict:
		#Create the standard header structure and load with a User Agent to ensure we get back a response.
		header = {'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US;rv:1.9.2.3) Gecko/20100401 Firefox/3.6.3 ( .NET CLR 3.5.30729)', }
	else:
		header = []
		header.append('User-Agent: Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US;rv:1.9.2.3) Gecko/20100401 Firefox/3.6.3 ( .NET CLR 3.5.30729)')

	printl2("", "__common__::getUserAgentHeader", "C")
	return header

#===========================================================================
#
#===========================================================================


def encodeThat(stringToEncode):
	#printl2("", "__common__::encodeThat", "S")
	if PY2:
		try:
			encodedString = stringToEncode.encode('utf-8', "ignore")
		except Exception:
			encodedString = stringToEncode
	else:
		return stringToEncode

	#printl2("", "__common__::encodeThat", "C")
	return encodedString

#===========================================================================
#
#===========================================================================


def getMyIp():
	#printl2("", "__common__::getMyIp", "S")
	import socket

	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		# a UDP "connect" only asks the kernel to pick the outbound route/local
		# address, no packet is actually sent - using a plain IP literal here
		# (instead of a hostname) means this keeps working even without a DNS
		# resolver or internet reachability, which matters because the
		# Jellyfin subnet scan (DPH_JellyfinDiscovery) needs the local IP to
		# even start, regardless of whether the box can reach the internet.
		s.connect(('10.255.255.255', 1))
		myIp = s.getsockname()[0]

		#printl2("", "__common__::getMyIp", "S")
		return str(myIp)
	except Exception:
		#printl2("", "__common__::getMyIp", "S")
		return False

#===========================================================================
#
#===========================================================================


def timeToMillis(time):
	return (time['hours'] * 3600 + time['minutes'] * 60 + time['seconds']) * 1000 + time['milliseconds']

#===========================================================================
#
#===========================================================================


def millisToTime(t):
	millis = int(t)
	seconds = millis / 1000
	minutes = seconds / 60
	hours = minutes / 60
	seconds %= 60
	minutes %= 60
	millis %= 1000
	return {'hours': hours, 'minutes': minutes, 'seconds': seconds, 'milliseconds': millis}

#===========================================================================
#
#===========================================================================


def getXMLHeader():
	#printl("", "getXMLHeader", "S")

	#printl("", "getXMLHeader", "C")
	return '<?xml version="1.0" encoding="utf-8"?>' + "\r\n"

#===========================================================================
#
#===========================================================================


def getOKMsg():
	#printl("", "getOKMsg", "S")

	#printl("", "getOKMsg", "C")
	return getXMLHeader() + '<Response code="200" status="OK" />'

#===========================================================================
#
#===========================================================================


def getServerHeaders(serverType=None):
	#printl("", "getServerHeaders", "S")

	if serverType is None:
		return {}

	from . import ServerSettings  # see the note on the TYPE_CHECKING import above
	ss: ServerSettingsData = ServerSettings[serverType]
	if ss is None:
		return {}
	else:
		sf: AbstractServerSettingsFactory = ss.factoryClass()
		return sf.getServerHeaders()

@dataclass
class DiscoveredServer:
	type: str
	server: str | None = None
	discovery: str | None = None
	owned: str | None = None
	master: int | None = None
	role: str | None = None
	clazz: any = None
	contentType: str | None = None
	uuid: str | None = None
	serverName: str | None = None
	port: int | None = None
	updated: str | None = None
	version: str | None = None

@dataclass
class EntryServer:
	name: str
	serverHost: str
	serverPort: str | None
	username: str | None
	active: str | None
	settings: AbstractServerSettings