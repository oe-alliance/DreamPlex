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
import sys
import os
import binascii
import datetime
import shutil
import math
import time
import uuid
import glob
import threading
from six import PY2

from enigma import addFont, loadPNG, loadJPG, getDesktop
from skin import loadSkin
from Components.config import config
from Components.AVSwitch import AVSwitch

try:
	from twisted.internet import reactor
except ImportError:
	reactor = None

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
version = "2.3.0"
boxResoltion = None
skinAuthors = ""
skinResolution = "HD"
skinCompatibility = "v2"
skinDebugMode = False
skinHighlightedColor = "#e69405"
skinNormalColor = "#ffffff"
skinFolder = None
g_boxData = None
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

	debugMode = config.plugins.dreamplex.debugMode.value

	if debugMode:

		offset = string.find("X-Plex-Token")
		if not string.find("X-Plex-Token") == -1:
			steps = 8
			start = offset + 13
			end = start + steps
			new_string = string[0:start] + "********" + string[end:]
			string = new_string

		if obfuscate is True:
			string = string[:-steps]
			for i in range(steps):
				string += "*"

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


def runInThread(work, onDone):
	"""
	Run a blocking call (network I/O) in a worker thread and deliver the
	result back on the enigma2 main loop.

	DreamPlex talks to the PMS and to plex.tv synchronously. Done on the
	main thread that freezes the whole enigma2 GUI while a request is in
	flight - and a long enough freeze makes enigma2 die (the image's hang
	detector kills it), which is exactly what an unreachable plex.tv used
	to do. Keep the callers' logic untouched, just move the waiting off
	the main loop.

	@param work: callable executed in the worker thread
	@param onDone: callable(result, error) executed on the main loop
	"""
	printl2("", "__common__::runInThread", "S")

	if reactor is None:
		# no reactor (offline tests): stay synchronous
		try:
			onDone(work(), None)
		except Exception as e:
			onDone(None, e)

		printl2("", "__common__::runInThread", "C")
		return

	def worker():
		try:
			result, error = work(), None
		except Exception as e:
			result, error = None, e

		# hop back onto the main loop before touching any GUI state
		reactor.callFromThread(onDone, result, error)

	thread = threading.Thread(target=worker)
	thread.daemon = True
	thread.start()

	printl2("", "__common__::runInThread", "C")

#===============================================================================
#
#===============================================================================


def fireAndForget(work):
	"""
	Run a blocking call in a worker thread and ignore its result. Used for
	reports we do not need an answer from (progress/scrobble, transcoder
	keep-alive) - they must never stall the GUI.
	"""
	def onDone(result, error):
		if error is not None:
			printl2("background request failed: " + str(error), "__common__::fireAndForget", "W")

	runInThread(work, onDone)

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
	cachePath = config.plugins.dreamplex.cachefolderpath.value

	try:
		os.chdir(cachePath)
		files = glob.glob('*.cache')
		for filename in files:
			os.unlink(filename)

		printl2("", "__common__::revokeCacheFiles", "C")

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
	if config.plugins.dreamplex.writeDebugFile.value:
		try:
			instance = Singleton()
			if instance.getLogFileInstance() == "":
				openLogFile()
				gLogFile = instance.getLogFileInstance()
				gLogFile.truncate()
			else:
				gLogFile = instance.getLogFileInstance()

			now = datetime.datetime.now()
			gLogFile.write("%02d:%02d:%02d.%07d " % (now.hour, now.minute, now.second, now.microsecond) + " >>> " + str(
				dmode) + " <<<  " + str(out) + "\n")
			gLogFile.flush()

		except Exception as ex:
			config.plugins.dreamplex.writeDebugFile.value = False
			config.plugins.dreamplex.debugMode.save()

			printl2("Exception(" + str(type(ex)) + "): " + str(ex), "__common__::writeToLog", "E")

#===============================================================================
#
#===============================================================================


def openLogFile():
	"""
	singleton instance for logfile
	"""
	#printl2("", "openLogFile", "S")

	logDir = config.plugins.dreamplex.logfolderpath.value

	try:
		if os.path.exists(logDir + "dreamplex_former.log"):
			os.remove(logDir + "dreamplex_former.log")

		if os.path.exists(logDir + "dreamplex.log"):
			shutil.copy2(logDir + "dreamplex.log", logDir + "dreamplex_former.log")

		instance = Singleton()
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
	except:
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
	except:
		printl2("exception, returning FALSE", "__common__::testInetConnectivity", "D")
		printl2("", "__common__::testInetConnectivity", "C")
		return False

#===============================================================================
#
#===============================================================================


def testPlexConnectivity(ip, port):
	"""
	test if the plex server is online on the specified port

	@param ip: e.g. 192.168.0.1
	@param port: e.g. 32400
	@return: bool
	"""
	printl2("", "__common__::testPlexConnectivity", "S")

	import socket

	sock = socket.socket()

	printl2("IP => " + str(ip), "__common__::testPlexConnectivity", "I")
	printl2("PORT => " + str(port), "__common__::testPlexConnectivity", "I")

	try:
		sock.settimeout(5)
		sock.connect((ip, port))
		sock.close()

		printl2("", "__common__::testPlexConnectivity", "C")
		return True
	except socket.error as e:
		printl2("Strange error creating socket: %s" % e, "__common__::testPlexConnectivity", "E")
		sock.close()

		printl2("", "__common__::testPlexConnectivity", "C")
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


def boxSupportsHdr(root=""):
	"""True when HDR video would reach the screen as HDR: the box can output
	it, the user has not turned it off, and the TV takes it.

	A box without HDR cannot show an HDR stream: a transcode that keeps its
	BT.2020/HLG signalling comes out black (measured with Emby on a Zgemma
	H8.2H by the DreamFin fork, 2026-10-05; whether Plex tone-maps it depends
	on the server). A box that CAN do HDR is not necessarily DOING it: the
	settings and TV checks were suggested here and written and measured by
	DreamFin on an SF8008 with an HDR and an SDR monitor. Shared code with
	that fork (f278be2). root is for the tests."""
	if not _boxCanOutputHdr(root):
		return False
	if _userTurnedHdrOff(root):
		return False
	return _tvTakesHdr(root) is not False


def _readProc(path, binary=False):
	try:
		with open(path, "rb" if binary else "r") as handle:
			return handle.read()
	except (IOError, OSError):
		return None


def _boxCanOutputHdr(root):
	"""What OpenATV 7.0 and 8.0 read to offer the HDR settings
	(Components/AVSwitch): Broadcom boxes have hlg_support_choices, Amlogic ones
	the amhdmitx config, HiSilicon ones hdmi_hdrtype (with its choices). And a
	box that offers no 2160p video mode does not count: the Zgemma H8.2H, a
	1080p chip (hi3716mv430), lists "dolby hdr10 hlg" in hdmi_hdrtype_choices
	all the same."""
	modes = _readProc(root + "/proc/stb/video/videomode_choices")
	if modes is not None and "2160p" not in modes:
		return False
	if os.path.exists(root + "/proc/stb/hdmi/hlg_support_choices"):
		return True
	if os.path.exists(root + "/sys/class/amhdmitx/amhdmitx0/config"):
		return True
	choices = _readProc(root + "/proc/stb/video/hdmi_hdrtype_choices")
	if choices is not None:
		return "hdr10" in choices.lower() or "hlg" in choices.lower()
	return os.path.exists(root + "/proc/stb/video/hdmi_hdrtype")


def _userTurnedHdrOff(root):
	"""The video settings the box obeys: HiSilicon's HDR type set to "none"
	(SDR in the menu), or Broadcom's HLG and HDR10 support both set to "no"."""
	hdrType = _readProc(root + "/proc/stb/video/hdmi_hdrtype")
	if hdrType is not None and hdrType.strip().lower() == "none":
		return True
	hlg = _readProc(root + "/proc/stb/hdmi/hlg_support")
	hdr10 = _readProc(root + "/proc/stb/hdmi/hdr10_support")
	return (hlg is not None and hdr10 is not None
			and hlg.strip().lower() == "no" and hdr10.strip().lower() == "no")


def _tvTakesHdr(root):
	"""Whether the TV's EDID announces HDR: True, False, or None when it cannot
	be told (no EDID, or a cut one). The paths are those eAVControl reads for
	OpenATV's own EDID page; Amlogic hands it over as hex text."""
	for path in ("/proc/stb/hdmi/raw_edid", "/sys/class/amhdmitx/amhdmitx0/rawedid"):
		raw = _readProc(root + path, binary=True)
		if raw:
			return edidTakesHdr(raw)
	return None


_HEX_TEXT = bytearray(b"0123456789abcdefABCDEF \t\r\n")  # ints on py2 and py3 alike


def edidTakesHdr(raw):
	"""True when an EDID announces HDR video - a CTA-861 HDR Static Metadata
	block with the PQ or HLG curve, or a Dolby Vision block -, False when it is
	complete and does not, None when it cannot be told."""
	edid = bytearray(raw)
	text = bytes(edid).strip()
	if text and all(c in _HEX_TEXT for c in bytearray(text)):
		try:
			edid = bytearray(binascii.unhexlify(b"".join(text.split())))
		except (TypeError, ValueError, binascii.Error):
			return None
	if len(edid) < 128 or edid[:8] != bytearray(b"\x00\xff\xff\xff\xff\xff\xff\x00"):
		return None
	extensions = edid[126]
	if len(edid) < 128 * (1 + extensions):
		return None  # cut short: the blocks that would say are missing
	for number in range(1, extensions + 1):
		block = edid[128 * number:128 * (number + 1)]
		if block[0] != 0x02:  # not a CTA-861 extension
			continue
		end = min(block[2], 127)  # the data blocks end where the timings start
		index = 4
		while index < end:
			tag, length = block[index] >> 5, block[index] & 0x1f
			payload = block[index + 1:index + 1 + length]
			if tag == 7 and len(payload) >= 2:  # extended tag
				if payload[0] == 6 and payload[1] & 0x0c:  # HDR static metadata: PQ or HLG
					return True
				if payload[0] == 1 and len(payload) >= 4 and payload[1:4] == bytearray(b"\x46\xd0\x00"):
					return True  # Dolby Vision vendor block (OUI 00-D0-46)
			index += 1 + length
	return False

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


def loadPlexSkin():
	"""
	loads the corresponding skin.xml file

	@param: none
	@return none
	"""
	printl2("", "__common__::loadPlexSkin", "S")

	currentSkin = getSkinFolder() + "/skin.xml"

	loadSkin(currentSkin)

	printl2("", "__common__::loadPlexSkin", "C")

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

	playerTempFolder = config.plugins.dreamplex.playerTempPath.value
	logFolder = config.plugins.dreamplex.logfolderpath.value
	mediaFolder = config.plugins.dreamplex.mediafolderpath.value
	configFolder = config.plugins.dreamplex.configfolderpath.value
	cacheFolder = config.plugins.dreamplex.cachefolderpath.value
	homeUsersFolder = config.plugins.dreamplex.configfolderpath.value

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


def getServerFromURL(url):  # CHECKED
	"""
	Simply split the URL up and get the server portion, sans port

	@param url: with or without protocol
	@return: the server URL
	"""
	printl2("", "__common__::getServerFromURL", "S")

	if url[0:4] == "http" or url[0:4] == "plex":

		printl2("", "__common__::getServerFromURL", "C")
		return url.split('/')[2]
	else:

		printl2("", "__common__::getServerFromURL", "C")
		return url.split('/')[0]

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


def newPlaybackId():
	"""Fresh id for ONE playback, used as X-Plex-Session-Identifier.

	getUUID() identifies the box for as long as the plugin runs; this one
	has to change with every media started, because the server keys the
	session it shows in its dashboard on it.
	"""
	return str(uuid.uuid4())

#===============================================================================
#
#===============================================================================


class PlaybackClock(object):
	"""Wall-clock estimate of the play position.

	enigma2 has no position to offer for a transcoded HLS stream -
	getPlayPosition() answers (-1, garbage) on every single tick - so
	somebody has to keep the time or the server can never be told where
	playback is. Seconds are counted while running and the caller syncs
	in the decoder position whenever that one IS valid, so plain files
	stay sample-accurate and HLS gets an honest estimate.
	"""

	def __init__(self, timeSource=None):
		self._time = timeSource or time.time
		self._base = 0
		self._mark = None  # wall time the clock started running, None = paused

	def start(self, seconds=0):
		self._base = max(0, int(seconds))
		self._mark = self._time()

	def pause(self):
		if self._mark is not None:
			self._base = self.tell()
			self._mark = None

	def resume(self):
		if self._mark is None:
			self._mark = self._time()

	def syncTo(self, seconds):
		"""Adopt a known-good position, keeping the running state."""
		self._base = max(0, int(seconds))
		if self._mark is not None:
			self._mark = self._time()

	def add(self, seconds):
		"""Follow a relative jump (skip keys); clamped at zero."""
		self.syncTo(self.tell() + int(seconds))

	def tell(self):
		if self._mark is None:
			return int(self._base)

		return int(self._base + (self._time() - self._mark))

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


def getSkinFolder():
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

	try:
		size = int(size)
	except (TypeError, ValueError):
		size = 0

	if size <= 0:
		printl2("", "__common__::convertSize", "C")
		return '0 B'

	# the exponent is computed on bytes, so the table must start at bytes -
	# otherwise every unit is shifted one step up (GB shown as TB)
	size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
	i = int(math.floor(math.log(size, 1024)))
	i = min(i, len(size_name) - 1)
	p = math.pow(1024, i)
	s = round(size / p, 2)

	printl2("", "__common__::convertSize", "C")
	return '%s %s' % (s, size_name[i])

#===========================================================================
#
#===========================================================================


def buildMediaChoiceName(items):
	"""Display label for one entry of the "Select media to play" dialog.

	items is one entry of the parts list from getMediaOptionsToPlay():
	(key, file, container, size, duration[, videoResolution, videoCodec, mediaIndex, videoRange])
	videoRange is "" for SDR, else the HDR kind ("HLG", "HDR10", ...).

	Always returns a native str: on Python 2 the enigma2 listbox renders a
	unicode label (any non-ascii file name) as "<not a string>".
	"""
	printl2("", "__common__::buildMediaChoiceName", "S")

	if items[1] is not None:
		name = items[1].split('/')[-1]
	else:
		size = convertSize(int(items[3]))
		duration = time.strftime('%H:%M:%S', time.gmtime(int(items[4])))
		# this is the case when there is no information of the real file name
		name = items[0] + " (" + items[2] + " / " + size + " / " + duration + ")"

	# prefix the VERSION properties (resolution/codec/size) so
	# multi-version items are distinguishable
	versionBits = []
	if len(items) > 5 and items[5]:
		versionBits.append("%s" % (items[5],))
	if len(items) > 6 and items[6]:
		versionBits.append("%s" % (items[6],))
	if len(items) > 8 and items[8]:
		versionBits.append("%s" % (items[8],))
	if versionBits:
		try:
			if items[3]:
				versionBits.append(convertSize(int(items[3])))
		except Exception:
			pass
		name = "[" + " / ".join(versionBits) + "]  " + name

	printl2("", "__common__::buildMediaChoiceName", "C")
	return encodeThat(name)

#===========================================================================
#
#===========================================================================


def getRatingValue(details):
	"""Return a 0-10 popularity score for a Plex item.

	Modern Plex Media Server reports the community score as "audienceRating";
	the legacy "rating" is only present when there is a separate critic score.
	Prefer the critic rating, then the audience rating, then the user's own
	rating, so the star widget is not left empty for items that do have a score.
	"""
	for key in ("rating", "audienceRating", "userRating"):
		try:
			value = float(details.get(key, 0) or 0)
		except (ValueError, TypeError):
			value = 0.0
		if value:
			return value
	return 0.0

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
	boxName = config.plugins.dreamplex.boxName.value

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
		except:
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
		s.connect(('google.com', 0))
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


def getPlexHeaders():
	#printl("", "getPlexHeaders", "S")

	plexHeader = {
		"Content-type": "application/x-www-form-urlencoded",
		"X-Plex-Version": getVersion(),
		"X-Plex-Client-Identifier": getUUID(),
		"X-Plex-Provides": "player",
		"X-Plex-Product": "DreamPlex",
		"X-Plex-Device-Name": config.plugins.dreamplex.boxName.value,
		"X-Plex-Platform": "Enigma2",
		"X-Plex-Model": "Enigma2",
		"X-Plex-Device": "stb",
	}

	# if settings['myplex_user']:
	# plexHeader["X-Plex-Username"] = settings['myplex_user']

	#printl("", "getPlexHeaders", "C")
	return plexHeader
