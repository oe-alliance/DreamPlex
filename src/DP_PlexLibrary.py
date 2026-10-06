# -*- coding: utf-8 -*-
"""
DreamPlex Plugin by DonDavici, 2012
and jbleyel 2021

Original -> https://github.com/oe-alliance/DreamPlex
Fork -> https://github.com/oe-alliance/DreamPlex

special thx to hippojay for his great work in plexbmc
which was the the base for this lib :-)

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
import os
import ssl
import socket
import sys
import traceback
from six import PY2, PY3
# import uuid
try:
	import cPickle as pickle
except:
	import pickle

try:
	from http.client import HTTPConnection, HTTPSConnection
except:
	from httplib import HTTPConnection, HTTPSConnection

try:
	from urllib.parse import quote_plus, unquote, urljoin
	from urllib.request import urlopen, Request
except:
	from urllib import quote_plus, unquote
	from urllib2 import urlopen, Request
	from urlparse import urljoin

from base64 import b64encode
from Components.config import config
from random import seed
from Tools.Directories import fileExists, copyfile

from Screens.Screen import Screen

from .__plugin__ import getPlugin, Plugin
from .__common__ import printl2 as printl, getXmlContent, getPlexHeader, encodeThat, getUUID, newPlaybackId, revokeCacheFiles, boxSupportsHdr
from . import _, defaultPluginFolderPath  # _ is translation

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
		etree = None
		raise Exception

#===============================================================================
#
#===============================================================================
#The method seed() sets the integer starting value used in generating random numbers. Call this function before calling any other random module function.
seed()

#===============================================================================
#
#===============================================================================
DEFAULT_PORT = "32400"
PLEXTV_SERVER = "plex.tv"

#===============================================================================
#
#===============================================================================


def videoRangeOfPart(part):
	"""HDR kind of one version, read from its video stream: "DV", "HDR10",
	"HLG", or "" for SDR.

	Plex puts no range on <Media>: it tells by the video stream's transfer
	characteristic (colorTrc) and its Dolby Vision flag (DOVIPresent).
	"""
	streams = part.getiterator('Stream') if PY2 else part.iter('Stream')
	for stream in streams:
		if stream.get('streamType') != "1":
			continue
		if stream.get('DOVIPresent') in ("1", "true"):
			return "DV"
		transfer = (stream.get('colorTrc') or "").lower()
		if transfer == "smpte2084":
			return "HDR10"
		if transfer == "arib-std-b67":
			return "HLG"
		return ""
	return ""

#===============================================================================
# PlexLibrary
#===============================================================================


class PlexLibrary(Screen):

	g_sessionID = None
	# one X-Plex-Session-Identifier per playback: this is what lets the
	# server tie the stream and the timeline reports together and show the
	# box in its "now playing" dashboard. Without it the reports still move
	# the resume point, but no session ever appears.
	g_playSessionID = None
	g_sections = []
	serverConfig_Name = "Plexserver"
	g_host = "192.168.45.190"
	serverConfig_port = "32400"
	g_currentServer = None
	serverConfig_connectionType = None
	g_showForeign = True
	g_address = None  # is later the combination of g_host : serverConfig_port
	serverConfig_playbackType = None
	g_stream = "0"  # 0 = linux local mount override, 1 = Selecting stream, 2 = smb/unc override 3 = transcode!?!?!
	g_useFilterSections = "true"  # show filter for media
	g_streamControl = "1"  # 1 unknown, 2 = unknown, 3 = All subs disabled
	g_channelview = "false"  # unknown
	g_flattenShow = False  # False = show seasons, True = show all
	g_playtheme = "false"
	g_forcedvd = "false"
	g_skipmetadata = "false"  # best understanding when looking getMoviesfromsection
	g_skipmediaflags = "false"  # best understanding when looking getMoviesfromsection
	g_skipimages = "false"
	g_loc = defaultPluginFolderPath[:-1]  # homeverzeichnis
	g_myplex_username = ""
	g_myplex_password = ""
	serverConfig_myplexToken = ""
	serverConfig_accessToken = ""
	g_myplex_accessToken = ""
	g_accessTokenDictHeader = ""
	g_accessTokenUrlHeader = ""
	g_transcode = "true"
	g_wolon = "true"
	g_wakeserver = "00-11-32-12-C5-F9"
	g_woldelay = 10
	g_nasoverride = "false"
	g_nasoverrideip = "192.168.45.190"
	g_nasuserid = "username"
	g_naspass = "password"
	g_nasroot = "Video"
	g_bonjour = "0"  # 0 = OFF, 1= ON
	serverConfig_quality = None
	g_capability = ""
	g_audioOutput = "2"  # 0 = "mp3,aac", 1 = "mp3,aac,ac3", 2 ="mp3,aac,ac3,dts"
	g_session = None
	g_serverConfig = None
	g_error = False
	g_showUnSeenCounts = False

	##################

	##################
	g_serverDict = []
	g_serverVersion = None
	g_myplex_accessTokenDict = {}
	g_sectionCache = None
	g_multiUser = False  # this is only true if we use plex.tv Connection and we have a plexPlass Account active on the server
	seenPic = "seen-fs8.png"
	unseenPic = "unseen-fs8.png"
	startedPic = "started-fs8.png"
	authHeader = None
	lastHeaderForServer = None
	lastResponse = None
	lastError = None
	fallback = ""
	http = "http"

	g_setSubtitleById_None = False  # mh
	g_SelectedEmbeddedSubtitleData = None  # mh

	#===========================================================================
	#
	#===========================================================================

	def __init__(self, session, serverConfig=None, resolvedMyPlexAddress=None, machineIdentifier=None):
		printl("", self, "S")

		Screen.__init__(self, session)

		self.g_error = False
		printl("running on " + str(sys.version_info), self, "I")

		# per-address cache of section uuid -> numeric section id
		self.g_sectionKeyMaps = {}

		# version (mediaIndex) chosen in the playback dialog, consumed by
		# transcode() so the universal transcoder serves the right file
		self.g_selectedMediaIndex = None

		# global serverConfig
		self.g_serverConfig = serverConfig

		# global settings
		self.g_useFilterSections = config.plugins.dreamplex.showFilter.value
		self.g_showUnSeenCounts = config.plugins.dreamplex.showUnSeenCounts.value
		self.g_sessionID = getUUID()

		# server settings
		self.serverConfig_Name = str(self.g_serverConfig.name.value)
		self.serverConfig_connectionType = str(self.g_serverConfig.connectionType.value)
		self.serverConfig_port = str(self.g_serverConfig.port.value)
		self.serverConfig_quality = str(self.g_serverConfig.quality.value)
		self.serverConfig_myplexToken = str(self.g_serverConfig.myplexToken.value)
		self.serverConfig_myplexLocalToken = str(self.g_serverConfig.myplexLocalToken.value)
		self.serverConfig_playbackType = self.g_serverConfig.playbackType.value
		self.serverConfig_localAuth = self.g_serverConfig.localAuth.value

		# manual token; getattr keeps configs saved by older versions working
		accessTokenConfig = getattr(self.g_serverConfig, "accessToken", None)
		if accessTokenConfig is not None:
			self.serverConfig_accessToken = str(accessTokenConfig.value).strip()
		else:
			self.serverConfig_accessToken = ""

		# PLAYBACK TYPES
		self.g_segments = self.g_serverConfig.segments.value  # is needed here because of fallback

		self.setPlaybackType(self.serverConfig_playbackType)

		printl("using this debugMode: " + str(config.plugins.dreamplex.debugMode.value), self, "D")
		printl("using this serverName: " + self.serverConfig_Name, self, "I")
		printl("using this connectionType: " + self.serverConfig_connectionType, self, "I")

		# CONNECTIONS TYPES
		if self.serverConfig_connectionType == "2":  # plex.tv
			self.setMyPlexData()

		elif self.serverConfig_connectionType == "0":  # IP
			self.setIpData()

			if self.serverConfig_localAuth:
				self.setMyPlexData()

		else:  # DNS
			try:
				self.g_host = str(socket.gethostbyname(self.g_serverConfig.dns.value))
				printl("using this FQDN: " + self.g_serverConfig.dns.value, self, "I")
				printl("found this ip for fqdn: " + self.g_host, self, "I")
				printl("using this serverPort: " + self.serverConfig_port, self, "I")
			except Exception as e:
				printl("socket error: " + str(e), self, "W")
				printl("trying fallback to ip", self, "I")
				self.g_host = "%d.%d.%d.%d" % tuple(self.g_serverConfig.ip.value)

		# if self.g_error is True:
		# 	self.leaveOnError()
		# else:
		#Fill serverdata to global g_serverDict
		self.prepareServerDict(resolvedMyPlexAddress, machineIdentifier)

		printl("", self, "C")

	#============================================================================
	#
	#============================================================================
	def setPlaybackType(self, myType):
		if myType == "0":  # STREAMED
			self.g_stream = "1"
			self.g_transcode = "false"

		elif myType == "1":  # TRANSCODED
			self.g_stream = "1"
			self.g_transcode = "true"
			self.g_segments = self.g_serverConfig.segments.value

			printl("using transcode: " + str(self.g_transcode), self, "I")
			printl("using this transcoding quality: " + str(self.serverConfig_quality), self, "I")
			printl("using this segments size: " + str(self.g_segments), self, "I")

		elif myType == "2":  # DIRECT LOCAL
			self.g_stream = "0"
			self.g_transcode = "false"

		# elif myType == "3": # DIRECT REMOTE
		# 	self.g_stream = "2"
		# 	self.g_transcode = "false"
		# 	self.g_nasoverride = "true"
		# 	self.g_nasoverrideip = "%d.%d.%d.%d" % tuple(self.g_serverConfig.nasOverrideIp.value)
		# 	self.g_nasuserid = str(self.g_serverConfig.smbUser.value)
		# 	self.g_naspass = str(self.g_serverConfig.smbPassword.value)
		# 	self.g_nasroot = str(self.g_serverConfig.nasRoot.value)
#===============================================================================
# LIBRARY ACCESS
#===============================================================================
	#===========================================================================
	#
	#===========================================================================
	def getSectionTypes(self):
		printl("", self, "S")

		fullList = []
		entryData = {}
		fullList.append((_("Movies"), Plugin.MENU_MOVIES, "movieEntry", entryData))
		fullList.append((_("Tv Shows"), Plugin.MENU_TVSHOWS, "showEntry", entryData))
		fullList.append((_("Music"), Plugin.MENU_MUSIC, "musicEntry", entryData))

		extend = False  # SWITCH

		if extend:
			fullList.append((_("Pictures"), Plugin.MENU_PICTURES, "pictureEntry", entryData))
			fullList.append((_("Channels"), Plugin.MENU_CHANNELS, "channelEntry", entryData))

		printl("mainMenuList: " + str(fullList), self, "D")
		printl("", self, "C")
		return fullList

	def getServerSectionPaths(self):
		sectionpaths = []

		if self.serverConfig_connectionType == "2":
			return []

		# sections tree
		tree = self.getAllSectionsXmlTree()
		if not tree:
			printl("getAllSectionsXmlTree: none", self, "D")
			return []

		entries = tree.findall('Directory')
		for entry in entries:
			# get paths
			spaths = entry.findall('Location')
			for spath in spaths:
				spathitems = dict(spath.items())
				if "path" in spathitems:
					pathvalue = spathitems['path']
					if pathvalue:
						if pathvalue[-1] != '/':
							pathvalue = pathvalue + '/'
						if pathvalue not in sectionpaths:
							sectionpaths.append(pathvalue)

		printl("getServerSectionPaths_All: " + str(sectionpaths), None, "D")

		_sectionpathsA = []
		_sectionpathsB = []

		for sectionpath in sectionpaths:
			_sectionpath = sectionpath[:-1]
			head, tail = os.path.split(_sectionpath)
			_sectionpathsA.append(head)

		_sectionpathsA_dict = {i: _sectionpathsA.count(i) for i in _sectionpathsA}
		for s, c in _sectionpathsA_dict.items():
			if c > 1:
				_sectionpathsB.append(s)

		_sectionpathsA = []
		_sectionpathsC = []

		for sectionpath in sectionpaths:
			found = False
			for sectionpathb in _sectionpathsB:
				if sectionpathb in sectionpath:
					found = True
					if sectionpathb not in _sectionpathsC:
						_sectionpathsC.append(sectionpathb)

			if not found:
				_sectionpathsA.append(sectionpath)

		sectionpaths = _sectionpathsC + _sectionpathsA
		_sectionpathsA = []
		for sectionpath in sectionpaths:
			if sectionpath[-1] != '/':
				sectionpath = sectionpath + '/'
			_sectionpathsA.append(sectionpath)

		sectionpaths = sorted(_sectionpathsA)

		printl("getServerSectionPaths_Filter: " + str(sectionpaths), None, "D")
		return sectionpaths

	#============================================================================
	#
	#============================================================================

	def getAllSections(self, myFilter=None, serverFilterActive=False):
		printl("getAllSections", self, "S")
		printl("myFilter: " + str(myFilter), self, "D")

		fullList = []
		serverList = []
		sharedServersCount = []
		entryData = None

		self.sectionCacheLoaded = False
		if config.plugins.dreamplex.useCache.value:
			# load section cache
			self.loadSectionCache()

		# sections tree
		tree = self.getAllSectionsXmlTree()

		if not tree:
			return [], {}
		else:
			entries = tree.findall('Directory')
			counter = 0

			printl("entries: " + str(entries), self, "D")

			summerizeServers = config.plugins.dreamplex.summerizeServers.value

			if summerizeServers and not serverFilterActive and self.serverConfig_connectionType == "2":

				for entry in entries:
					counter += 1
					entryData = (dict(entry.items()))

					# first we check if there are more servers over sharing involed
					if self.serverConfig_connectionType == "2":
						if "serverName" in entryData:
							if str(entryData['serverName']) not in sharedServersCount:
								sharedServersCount.append(str(entryData['serverName']))

								if "sourceTitle" in entryData:
									serverName = str(entryData['sourceTitle'])
								else:
									serverName = str(entryData['serverName'])
								entryData["myCurrentFilterData"] = myFilter
								serverList.append((serverName, Plugin.MENU_SERVERFILTER, "serverFilter", entryData))

				return serverList

			else:
				for entry in entries:
					counter += 1
					entryData = (dict(entry.items()))

					# first we check if there are more servers over sharing involed
					if self.serverConfig_connectionType == "2":
						if "serverName" in entryData:
							if str(entryData['serverName']) not in sharedServersCount:
								sharedServersCount.append(str(entryData['serverName']))

					if summerizeServers and serverFilterActive:
						if str(entryData['serverName']) != serverFilterActive:
							continue

					# set the source for the section data
					source = "plex"
					if config.plugins.dreamplex.useCache.value:
						source = self.updateSectionCache(entryData)

					entryData["source"] = source

					# add specific data to entryData if needed
					if self.serverConfig_connectionType == "2":  # plex.tv
						entryData["address"] = entryData['address'] + ":" + entryData['port']

						# we have to do this because via plex.tv there could be diffrent servers with other tokens
						if str(entryData.get('address')) not in self.g_myplex_accessToken:
							printl("section address" + str(entryData.get('address')), self, "D")
							#self.g_myplex_accessTokenDict[str(entryData.get('address'))] = str(entryData.get('accessToken', None))

						# finally we set AccessTokenHeader
						self.setAccessTokenHeader(address=str(entryData.get('address')), accessToken=str(entryData.get('accessToken', None)), serverVersion=str(entryData.get('serverVersion')))

						# modern plex.tv announces 'path'/'key' as a bare
						# per-share hash the PMS itself does not accept;
						# resolve it to the server's numeric section id
						entryData["path"] = self.resolveSectionPath(entryData)
					else:
						entryData["path"] = "/library/sections/" + entryData.get('key')
						entryData["address"] = str(self.g_host + ":" + self.serverConfig_port)

					if not self.g_useFilterSections and entryData.get('type') != 'artist':
						entryData["path"] += '/all'

					#entryData["serverName"] = self.serverConfig_Name.encode()
					entryData["contentUrl"] = self.getContentUrl(entryData['address'], entryData['path'])  # former t_url

					# marker for getSectionFilter: modern PMS answer /library/sections/<id>
					# without Directory children, so the filter menu must be synthesized
					entryData["isSectionRoot"] = True

					# if this is a plex.tv connection we look if we should provide more information for better overview since plex.tv combines all servers and shares
					detail = ""
					if config.plugins.dreamplex.showDetailsInList.value and self.serverConfig_connectionType == "2":
						if config.plugins.dreamplex.showDetailsInListDetailType.value == "1":
							if "sourceTitle" in entryData:
								detail = " \n( " + entryData['sourceTitle'] + ")"
							else:
								detail = " \n(" + str(entryData['serverName']) + ")"
						elif config.plugins.dreamplex.showDetailsInListDetailType.value == "2":
							if "serverName" in entryData:
								detail = " \n(" + str(entryData['serverName']) + ")"

					title = entryData.get('title')
					title = title.encode('utf-8') if PY2 else title
					entryName = _(title) + detail

					if entryData.get('type') == 'show':
						printl("_MODE_TVSHOWS detected", self, "D")
						if myFilter is not None and myFilter != "tvshow":
							continue

						if self.g_useFilterSections:
							fullList.append((entryName, Plugin.MENU_FILTER, "showEntry", entryData))
						else:
							fullList.append((_(title), getPlugin("tvshows", Plugin.MENU_TVSHOWS), "showEntry", entryData))

					elif entryData.get('type') == 'movie':
						printl("_MODE_MOVIES detected", self, "D")
						if (myFilter is not None) and (myFilter != "movies"):
							continue

						if self.g_useFilterSections:
							fullList.append((entryName, Plugin.MENU_FILTER, "movieEntry", entryData))
						else:
							fullList.append((_(title), getPlugin("movies", Plugin.MENU_MOVIES), "movieEntry", entryData))

					elif entryData.get('type') == 'artist':
						printl("_MODE_ARTISTS detected", self, "D")
						if (myFilter is not None) and (myFilter != "music"):
							continue

						# in case of music we use always filters
						fullList.append((entryName, Plugin.MENU_FILTER, "musicEntry", entryData))

					elif entryData.get('type') == 'photo':
						printl("_MODE_PHOTOS detected but excluded", self, "D")
						# if (myFilter is not None) and (myFilter != "photos"):
						# 	continue
						# if self.g_useFilterSections:
						# 	fullList.append((entryName, Plugin.MENU_FILTER, "pictureEntry", entryData))
						# else:
						# 	fullList.append((_(entryData.get('title').encode('utf-8')), getPlugin("pictures", Plugin.MENU_PICTURES), "movieEntry", entryData))

					else:
						raise Exception("we should not be here")

			# now the tokenDict should be filled
			printl("g_myplex_accessTokenDict: " + str(self.g_myplex_accessTokenDict), self, "D")

			if len(sharedServersCount) <= 1:
				if entryData is not None:
					onDeck = dict()
					onDeck["contentUrl"] = self.getContentUrl(entryData['address'], "/library/onDeck")
					onDeck["type"] = "movie"
					onDeck["currentViewMode"] = "movie"
					onDeck["nextViewMode"] = "mixed"
					#mh //fullList.append((_("onDeck"), getPlugin("mixed", Plugin.MENU_MIXED), "mixedEntry", onDeck))
					fullList.insert(0, (_("On Deck"), getPlugin("mixed", Plugin.MENU_MIXED), "mixedEntry", onDeck))

					recentlyAdded = dict()
					recentlyAdded["contentUrl"] = self.getContentUrl(entryData['address'], "/library/recentlyAdded")
					recentlyAdded["type"] = "movie"
					recentlyAdded["currentViewMode"] = "movie"
					recentlyAdded["nextViewMode"] = "mixed"
					#mh //fullList.append((_("New"), getPlugin("mixed", Plugin.MENU_MIXED), "mixedEntry", recentlyAdded))
					fullList.insert(1, (_("New"), getPlugin("mixed", Plugin.MENU_MIXED), "mixedEntry", recentlyAdded))

					if config.plugins.dreamplex.useCache.value:
						self.saveSectionCache()

			# as a last step we check if there where any content
			if counter == 0:
				self.lastError = _("No data in this section!")

		printl("", self, "C")
		return fullList

	#=============================================================================
	#
	#=============================================================================
	def resolveSectionPath(self, entryData):
		"""
		Old plex.tv answers carried path="/library/sections/<numeric id>".
		Modern ones only ship a bare per-share hash (e.g. "21b946...") in
		'path'/'key', which the PMS itself answers with 404. Resolve the
		numeric id by matching the section uuid against the server's own
		/library/sections listing (one request per server, cached).
		"""
		printl("", self, "S")

		path = str(entryData.get("path", ""))
		if path.startswith("/"):
			# legacy plex.tv format, nothing to resolve
			printl("", self, "C")
			return path

		address = str(entryData["address"])

		if address not in self.g_sectionKeyMaps:
			mapping = {}
			tree = self.getXmlTreeFromUrl("%s://%s/library/sections" % (self.http, address))
			if tree is not None:
				for directory in tree.findall("Directory"):
					uuid = directory.get("uuid")
					key = directory.get("key")
					if uuid and key:
						mapping[uuid] = key
			self.g_sectionKeyMaps[address] = mapping
			printl("section key map for %s: %s" % (address, str(mapping)), self, "D")

		numericKey = self.g_sectionKeyMaps[address].get(entryData.get("uuid"))

		if numericKey:
			entryData["key"] = numericKey
			printl("resolved section '%s' to numeric key %s" % (str(entryData.get("title")), numericKey), self, "D")
			printl("", self, "C")
			return "/library/sections/" + numericKey

		# last resort: prefix whatever key we have so the URL is well-formed
		fallbackKey = str(entryData.get("key") or path or "0")
		printl("no numeric key for section uuid %s, using %s" % (str(entryData.get("uuid")), fallbackKey), self, "W")
		printl("", self, "C")
		return "/library/sections/" + fallbackKey

	#=============================================================================
	#
	#=============================================================================
	def getSectionFilter(self, incomingEntryData):
		printl("", self, "S")
		printl("incomingEntryData: " + str(incomingEntryData), self, "D")

		# we need this for cache mechanism
		if "uuid" in incomingEntryData:
			printl("we have a uuid ...", self, "D")
			self.currentUuid = incomingEntryData["uuid"]

		if "type" in incomingEntryData:
			printl("we have a type ...", self, "D")
			self.type = incomingEntryData["type"]

		fullList = []
		# get xml from url
		tree = self.getXmlTreeFromUrl(incomingEntryData["contentUrl"])

		# no Element truthiness here: a childless container must reach the
		# synthesizer below, and Element.__bool__ is deprecated anyway
		if tree is not None:
			entries = tree.findall('Directory')
		else:
			entries = []
		counter = 0

		for entry in entries:
			counter += 1
			entryData = (dict(entry.items()))

			entryData["hasSecondaryTag"] = entryData.get("secondary", False)
			entryData["hasPromptTag"] = entryData.get("prompt", False)
			entryData["type"] = incomingEntryData["type"]

			title = entryData.get('title')
			title = title.encode('utf-8') if PY2 else title

			# the server names the "all" filter after the section on movie
			# libraries (e.g. "All Pel·lis"), so it never matches a catalogue
			# entry and shows untranslated; on show/artist libraries it is the
			# generic "All Shows"/"All Artists" which the catalogue does cover.
			# Use the same translatable label the synthesized menu uses, so
			# "Todos" is consistent regardless of section name or server.
			if entryData.get("key") == "all":
				sectionType = incomingEntryData.get("type")
				if sectionType in ("show", "episode"):
					label = _("All Shows")
				elif sectionType == "artist":
					label = _("All Artists")
				else:
					label = _("All Movies")
			else:
				label = _(title)

			# modern PMS ships the ready-to-use content path of a filter value
			# (e.g. /library/sections/1/all?genre=123) in the fastKey attribute;
			# the legacy contentUrl + "/" + key drill-in no longer exists there
			fastKey = entryData.get("fastKey")
			if fastKey:
				server = self.getServerFromURL(incomingEntryData["contentUrl"])
				entryData["contentUrl"] = "%s://%s%s" % (self.http, server, fastKey)
			else:
				entryData["contentUrl"] = incomingEntryData["contentUrl"] + "/" + entryData["key"]

			if entryData["hasSecondaryTag"]:  # means that the next answer is a filter
				fullList.append((label, Plugin.MENU_FILTER, "showFilter", entryData))

			else:
				if config.plugins.dreamplex.useCache.value:
					# we set this here now to have this information later
					if self.currentUuid in self.g_sectionCache:
						entryData["source"] = self.g_sectionCache[self.currentUuid]["source"]
					else:
						entryData["source"] = "plex"

					entryData["uuid"] = self.currentUuid
					entryData["type"] = self.type

				if incomingEntryData["type"] == 'show' or incomingEntryData["type"] == 'episode':
					fullList.append((label, getPlugin("tvshows", Plugin.MENU_TVSHOWS), "showEntry", entryData))

				elif incomingEntryData["type"] == 'movie':
					fullList.append((label, getPlugin("movies", Plugin.MENU_MOVIES), "movieEntry", entryData))

				elif incomingEntryData["type"] == 'artist':
					fullList.append((label, getPlugin("music", Plugin.MENU_MUSIC), "musicEntry", entryData))

				# elif incomingEntryData["type"] == 'photo':
				# 	printl( "_MODE_PHOTOS detected", self, "D")

				else:
					raise Exception("we should not be here")

			printl("entryData: " + str(entryData), self, "D")

		# modern PMS answers the section root without Directory children:
		# build the menu locally instead of failing with "No data"
		if counter == 0:
			if incomingEntryData.get("isSectionRoot", False) and tree is not None and tree.tag == "MediaContainer":
				printl("no filter children from PMS, synthesizing section menu", self, "I")
				fullList = self.getSynthesizedSectionFilter(incomingEntryData)

			if not fullList:
				self.lastError = _("No data in this section!")

		printl("", self, "C")
		return fullList

	#=============================================================================
	#
	#=============================================================================
	def getSynthesizedSectionFilter(self, incomingEntryData):
		"""
		Modern Plex Media Servers no longer answer /library/sections/<id>
		with the legacy secondary navigation (All/Unwatched/By Genre/...).
		Build that menu locally with the same tuple shapes getSectionFilter()
		produces, so DP_ServerMenu/DP_LibMain need no changes at all.
		"""
		printl("", self, "S")

		sectionType = incomingEntryData.get("type")
		rootUrl = incomingEntryData["contentUrl"]

		# (title, key, kind, extraData)
		# kind: None = content entry, "secondary" = next level is a filter
		# list, "prompt" = ask for a search string first
		if sectionType == 'movie':
			plugin = getPlugin("movies", Plugin.MENU_MOVIES)
			entryType = "movieEntry"
			menu = [
				(_("All Movies"), "all", None, None),
				(_("Unwatched"), "all?unwatched=1", None, None),
				(_("Recently Added"), "recentlyAdded", None, None),
				(_("Recently Released"), "newest", None, None),
				(_("On Deck"), "onDeck", None, None),
				(_("By Genre"), "genre", "secondary", None),
				(_("By Year"), "year", "secondary", None),
				(_("By Decade"), "decade", "secondary", None),
				(_("Search..."), "search?type=1", "prompt", None),
			]

		elif sectionType == 'show' or sectionType == 'episode':
			plugin = getPlugin("tvshows", Plugin.MENU_TVSHOWS)
			entryType = "showEntry"
			# recentlyAdded/onDeck answer episodes and seasons mixed together;
			# DP_LibShows switches to the direct Video+Directory parser for
			# exactly these key values
			menu = [
				(_("All Shows"), "all", None, None),
				(_("Unwatched"), "all?unwatched=1", None, None),
				(_("Recently Added"), "recentlyAdded", None, None),
				(_("On Deck"), "onDeck", None, None),
				(_("By Genre"), "genre", "secondary", None),
				(_("By Year"), "year", "secondary", None),
				(_("Search..."), "search?type=2", "prompt", None),
			]

		elif sectionType == 'artist':
			plugin = getPlugin("music", Plugin.MENU_MUSIC)
			entryType = "musicEntry"
			# recently added music answers albums, route it to the album parser
			menu = [
				(_("All Artists"), "all", None, None),
				(_("Recently Added"), "recentlyAdded", None,
					{"nextViewMode": "ShowAlbums", "currentViewMode": "ShowAlbums"}),
				(_("By Genre"), "genre", "secondary", None),
				(_("Search..."), "search?type=8", "prompt", None),
			]

		else:
			printl("unsupported section type: " + str(sectionType), self, "W")
			printl("", self, "C")
			return []

		fullList = []
		for title, key, kind, extraData in menu:
			entryData = {
				"title": title,
				"key": key,
				"type": sectionType,
				"contentUrl": rootUrl + "/" + key,
				"hasSecondaryTag": kind == "secondary",
				"hasPromptTag": kind == "prompt",
				"synthesized": True,
			}

			if extraData:
				entryData.update(extraData)

			if kind == "secondary":
				fullList.append((title, Plugin.MENU_FILTER, "showFilter", entryData))
			else:
				if config.plugins.dreamplex.useCache.value:
					currentUuid = getattr(self, "currentUuid", None)
					if currentUuid in self.g_sectionCache:
						entryData["source"] = self.g_sectionCache[currentUuid]["source"]
					else:
						entryData["source"] = "plex"

					entryData["uuid"] = currentUuid

				fullList.append((title, plugin, entryType, entryData))

			printl("synthesized entryData: " + str(entryData), self, "D")

		printl("", self, "C")
		return fullList

	#===========================================================================
	#
	#===========================================================================
	def getMoviesFromSection(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		printl("", self, "C")
		return self.getMediaData(url, tagType="Video", nextViewMode="play", currentViewMode="ShowMovies")

	#===========================================================================
	#
	#===========================================================================
	def getMixedContentFromSection(self, url, fromRemotePlayer=False):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		printl("", self, "C")
		return self.getMediaData(url, tagType="Video", nextViewMode="play", currentViewMode="ShowMovies", fromRemotePlayer=fromRemotePlayer)

	#===============================================================================
	#
	#===============================================================================
	def getMusicByArtist(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		printl("", self, "C")
		return self.getDirectoryData(url, nextViewMode="ShowAlbums", currentViewMode="ShowArtists")

	#===============================================================================
	#
	#===============================================================================
	def getMusicByAlbum(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		printl("", self, "C")
		return self.getMediaData(url, tagType="Track", nextViewMode="ShowTracks", currentViewMode="ShowAlbums")

	#===========================================================================
	#
	#===========================================================================
	def getMusicTracks(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		printl("", self, "C")
		return self.getMediaData(url, tagType="Track", nextViewMode="play", currentViewMode="ShowTracks")

	#=======================================================================
	#
	#=======================================================================
	def getShowsFromSection(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		fullList = []

		# get xml from url
		tree = self.getXmlTreeFromUrlPaged(url)
		server = str(self.getServerFromURL(url))
		# find coressponding tags in xml

		if not tree:
			return [], {}
		else:
			entries = tree.findall('Directory')

			# write global xml data to entryData
			mediaContainer = (dict(tree.items()))
			printl("mediaContainer: " + str(mediaContainer), self, "D")

			for entry in entries:
				entryData = (dict(entry.items()))
				printl("entryData: " + str(entryData), self, "D")

				entryData["currentViewMode"] = "ShowShows"
				entryData["nextViewMode"] = "ShowSeasons"
				entryData['server'] = server
				entryData['tagType'] = "Show"

				if "type" not in entryData:
					entryData["type"] = "show"

				entryData['genre'] = " / ".join(self.getListFromTag(entry, "Genre"))

				# now we populate entryData with the transcode data for images
				entryData = self.getImageData(entryData, entry, server)

				entryData['token'] = self.g_myplex_accessToken

				if mediaContainer.get("title2", "") != "By Folder":
					viewState = self.getViewStateForShowEntry(entryData)
					printl("viewState: " + str(viewState), self, "D")

#					if self.g_showUnSeenCounts:
#						entryData['title'] = entryData['title'] + " ("+ str(entryData["leafCount"]) + "/" + str(entryData["viewedLeafCount"]) + ")"
				else:
					entryData['tagType'] = "Directory"
					entryData["type"] = "Folder"
					viewState = None

				#Create URL based on whether we are going to flatten the season view
				if self.g_flattenShow:
					printl("Flattening all shows", self, "I")
					url = '%s://%s/%s' % (self.http, server, entryData['key'].replace("children", "allLeaves"))
				else:
					url = '%s://%s/%s' % (self.http, server, entryData['key'])

				# add to fullList
				fullList.append(self.getFullListEntry(entryData, url, viewState))

			printl("", self, "C")
			return fullList, mediaContainer

	#===========================================================================
	#
	#===========================================================================
	def getSeasonsOfShow(self, url):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		fullList = []

		# get xml from url
		tree = self.getXmlTreeFromUrlPaged(url)
		server = str(self.getServerFromURL(url))

		if not tree:
			return [], {}
		else:
			# find coressponding tags in xml
			entries = tree.findall('Directory')
			printl("entries: " + str(entries), self, "D")

			# write global xml data to entryData
			mediaContainer = (dict(tree.items()))
			printl("mediaContainer: " + str(mediaContainer), self, "D")

			for entry in entries:
				entryData = (dict(entry.items()))
				printl("entryData: " + str(entryData), self, "D")

				if self.g_flattenShow:
					url = self.http + '://' + server + entryData["key"]
					return self.getEpisodesOfSeason(url)

				entryData["currentViewMode"] = "ShowSeasons"
				entryData["nextViewMode"] = "ShowEpisodes"
				entryData['server'] = server
				entryData['tagType'] = "Episodes"

				# this is the case for show all epsiodes of show without season number
				if "type" not in entryData:
					entryData["type"] = "season"

				# now we populate entryData with the transcode data for images
				entryData = self.getImageData(entryData, entry, server)

				entryData['token'] = self.g_myplex_accessToken

				# if we are "all episodes" we do not have ratingKey - for this reason we set "key" as "ratingKey" form parent Mediacontainer but only if we are not in ByFolder mode
				if "ratingKey" not in entryData and mediaContainer.get("title2", "") != "By Folder" and "key" in mediaContainer:
					entryData["ratingKey"] = mediaContainer["key"]

				if mediaContainer.get("title2", "") != "By Folder":
					viewState = self.getViewStateForShowEntry(entryData)
				else:
					entryData['tagType'] = "Directory"
					entryData["type"] = "Folder"
					viewState = None

				url = '%s://%s/%s' % (self.http, server, entryData['key'])

				# add to fullList
				fullList.append(self.getFullListEntry(entryData, url, viewState))

			printl("fullList: " + str(fullList), self, "C")
			printl("", self, "C")
			return fullList, mediaContainer

	#===============================================================================
	#
	#===============================================================================
	def getImageData(self, entryData, entry, server, switchMedias=False):
		printl("", self, "S")

		if switchMedias:
			# we need this for example for episodes
			entryData['thumb'] = self.getImage(entry, server, myType="art")
			entryData['art'] = self.getImage(entry, server, myType="thumb")
		else:
			entryData['thumb'] = self.getImage(entry, server, myType="thumb")
			entryData['art'] = self.getImage(entry, server, myType="art")

		# in some cases there are other images
		if "parentThumb" in entryData:
			entryData['parentThumb'] = self.getImage(entry, server, myType="parentThumb")

		if "banner" in entryData:
			entryData['banner'] = self.getImage(entry, server, myType="banner")

		printl("", self, "C")
		return entryData
	#===============================================================================
	#
	#===============================================================================

	def getEpisodesOfSeason(self, url, directMode=False):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")
		nextViewMode = "play"

		if not directMode:
			currentViewMode = "ShowEpisodes"
		else:
			currentViewMode = "ShowEpisodesDirect"

		return self.getMediaData(url, tagType="Video", nextViewMode=nextViewMode, currentViewMode=currentViewMode, switchMedias=True)

	#===========================================================================
	#
	#===========================================================================
	def getMediaData(self, url, tagType, nextViewMode, currentViewMode, switchMedias=False, fromRemotePlayer=False):
		printl("", self, "S")
		fullList = []

		# get xml from url
		tree = self.getXmlTreeFromUrlPaged(url)
		server = str(self.getServerFromURL(url))

		if not tree:
			return [], {}
		else:
			# find coressponding tags in xml
			entries = tree.findall(tagType)

			if fromRemotePlayer:
				# if there are no entries it might be that we are music for this reason we search for Track as well
				if not entries:
					tagType = "Track"
					entries = tree.findall(tagType)

			# write global xml data to entryData
			mediaContainer = (dict(tree.items()))
			printl("mediaContainer: " + str(mediaContainer), self, "D")

			for entry in entries:
				entryData = (dict(entry.items()))
				printl("entryData: " + str(entryData), self, "D")

				entryData["currentViewMode"] = currentViewMode
				entryData["nextViewMode"] = nextViewMode
				entryData['server'] = server
				entryData['tagType'] = tagType
				if "index" in entryData:
					entryData['title'] = entryData["index"] + ". " + entryData["title"]
				entryData['genre'] = " / ".join(self.getListFromTag(entry, "Genre"))
				entryData['director'] = " / ".join(self.getListFromTag(entry, "Director"))
				entryData['cast'] = " / ".join(self.getListFromTag(entry, "Role"))
				entryData['writer'] = " / ".join(self.getListFromTag(entry, "Writer"))
				entryData['country'] = " / ".join(self.getListFromTag(entry, "Country"))

				# now we populate entryData with the transcode data for images
				entryData = self.getImageData(entryData, entry, server, switchMedias)

				entryData['token'] = self.g_myplex_accessToken

				# add part and media data to main data element
				mediaDataArr = self.getPartAndMediaDataFromEntry(entry)

				entryData["mediaDataArr"] = mediaDataArr

				# set seen state for picture handling in view
				seenVisu = self.getViewStatefromViewCount(entryData)

				# add to fullList
				fullList.append(self.getFullListEntry(entryData, url, seenVisu))

			# find coressponding tags in xml
			entries = tree.findall('Directory')

			for entry in entries:
				entryData = (dict(entry.items()))
				printl("directoryData: " + str(entryData), self, "D")

				entryData['server'] = str(server)
				entryData['tagType'] = "Directory"
				entryData["currentViewMode"] = currentViewMode
				entryData["nextViewMode"] = "ShowDirectory"
				if "type" not in entryData:
					entryData["type"] = "Folder"

				# dirty workaround for music
				if entryData["type"] == "album":
					entryData["nextViewMode"] = "ShowTracks"

				if entryData["type"] == "season":
					entryData["nextViewMode"] = "ShowEpisodes"
					entryData["title"] = entryData["parentTitle"] + " - " + _("Season") + " " + entryData["index"]

				# now we populate entryData with the transcode data for images
				entryData = self.getImageData(entryData, entry, server)

				# add to fullList
				fullList.append(self.getFullListEntry(entryData, url))

			printl("", self, "C")
			return fullList, mediaContainer

	#===============================================================================
	#
	#===============================================================================
	def getDirectoryData(self, url, nextViewMode, currentViewMode):
		printl("", self, "S")
		fullList = []

		# get xml from url
		tree = self.getXmlTreeFromUrlPaged(url)
		server = str(self.getServerFromURL(url))

		if not tree:
			return [], {}
		else:
			# find coressponding tags in xml
			entries = tree.findall("Directory")

			# write global xml data to entryData
			mediaContainer = (dict(tree.items()))
			printl("mediaContainer: " + str(mediaContainer), self, "D")

			for entry in entries:
				entryData = (dict(entry.items()))
				printl("entryData: " + str(entryData), self, "D")

				entryData['server'] = server
				entryData['tagType'] = "Directory"
				entryData["currentViewMode"] = currentViewMode
				entryData["nextViewMode"] = nextViewMode

				# now we populate entryData with the transcode data for images
				entryData = self.getImageData(entryData, entry, server)

				if "type" in entryData:
					if entryData["type"] == "album" or entryData["type"] == "artist":
						entryData['genre'] = " / ".join(self.getListFromTag(entry, "Genre"))
				else:
					entryData["type"] = "Folder"

				# add to fullList
				fullList.append(self.getFullListEntry(entryData, url))

			printl("", self, "C")
			return fullList, mediaContainer

	#===========================================================================
	#
	#===========================================================================s
	def getPartAndMediaDataFromEntry(self, entry):
		printl("", self, "S")
		mediaDataArr = []

		for child in entry:
			isMedia = False
			if child.tag == "Media":
				isMedia = True
				mediaData = (dict(child.items()))
				printl("mediaData: " + str(mediaData), self, "D")
				mediaData["Parts"] = []

			for babies in child:
				if babies.tag == "Part":
					partData = (dict(babies.items()))
					printl("partData:" + str(partData), self, "D")
					mediaData["Parts"].append(partData)

			if isMedia:
				mediaDataArr.append(mediaData)

		printl("", self, "C")
		return mediaDataArr

	#===========================================================================
	#
	#===========================================================================
	def setIpData(self):
		printl("", self, "S")

		self.g_host = "%d.%d.%d.%d" % tuple(self.g_serverConfig.ip.value)

		printl("using this serverIp: " + self.g_host, self, "I")
		printl("using this serverPort: " + self.serverConfig_port, self, "I")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setMyPlexData(self):
		printl("", self, "S")

		self.g_myplex_username = self.g_serverConfig.myplexUsername.value
		self.g_myplex_password = self.g_serverConfig.myplexPassword.value
		self.g_myplex_url = self.g_serverConfig.myplexUrl.value

		if self.serverConfig_myplexToken == "":
			printl("serverconfig: " + str(self.g_serverConfig), self, "D")
			self.serverConfig_myplexToken = self.getNewMyPlexToken()

			if self.serverConfig_myplexToken is False:
				self.g_error = True

			else:
				self.g_serverConfig.myplexTokenUsername.value = self.g_myplex_username
				self.g_serverConfig.myplexTokenUsername.save()
				self.g_serverConfig.myplexToken.value = self.serverConfig_myplexToken
				self.g_serverConfig.myplexToken.save()

		else:
			self.serverConfig_myplexToken = self.g_serverConfig.myplexToken.value

		printl("plex.tvUrl: " + str(self.g_myplex_url), self, "D")
		printl("plex.tv_username: " + str(self.g_myplex_username), self, "D", True, 10)
		printl("plex.tv_password: " + str(self.g_myplex_password), self, "D", True, 6)
		printl("plex.tv_token: " + str(self.serverConfig_myplexToken), self, "D", True, 6)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def prepareServerDict(self, resolvedMyPlexAddress, machineIdentifier):
		printl("", self, "S")

		self.g_serverDict = {}

		accessToken = None

		if self.serverConfig_connectionType == "2":  # plex.tv
			printl("Adding plex.tv as server location", self, "D")

			if resolvedMyPlexAddress is not None:  # this is the case if we come from remote player
				response = self.getSharedServerForPlexUser()
				servers = response.findall("Server")
				for server in servers:
					serverMachineIdentifier = server.get("machineIdentifier")
					if machineIdentifier == serverMachineIdentifier:
						accessToken = server.get("accessToken")

				self.g_serverDict = {'serverName': 'MYPLEX', 'address': resolvedMyPlexAddress, 'discovery': 'myplex', 'token': None, 'uuid': None, 'role': 'master'}
				self.g_currentServer = resolvedMyPlexAddress
			else:
				self.g_serverDict = {'serverName': 'MYPLEX', 'address': "my.plex.app", 'discovery': 'myplex', 'token': None, 'uuid': None, 'role': 'master'}

		else:
			if not self.g_host or self.g_host == "<none>":
				self.g_host = None

			elif not self.serverConfig_port:
				printl("No port defined. Using default of " + DEFAULT_PORT, self, "D")
				self.g_currentServer = self.g_host + ":" + DEFAULT_PORT

			else:
				self.g_currentServer = self.g_host + ":" + self.serverConfig_port
				printl("Settings hostname and port: " + self.g_currentServer, self, "D")

			if self.g_currentServer is not None:
				printl("g_currentServer: " + str(self.g_currentServer), self, "D")
				self.g_serverDict = {'serverName': self.serverConfig_Name, 'address': self.g_currentServer, 'discovery': 'local', 'token': None, 'uuid': None, 'role': 'master'}
			else:
				raise Exception

			# we have to set self.g_myplex_accessTokenDict here
			# because none will trigger empty tokens that are needed when we do not use plex.tv
			self.g_myplex_accessTokenDict = {}

			# just in case we use plex.tv also in local Lan we have to set the token data
			accessToken = None

			# precedence: manual token > local auth (plex.tv) tokens > nothing
			if self.serverConfig_accessToken:
				accessToken = self.serverConfig_accessToken

			elif self.serverConfig_localAuth:
				if self.serverConfig_myplexLocalToken:
					# this is the token we get from plex.tv if we are connected with a user that is not thw owner and should be limited to its sections as well
					#self.g_myplex_accessTokenDict[str(self.g_currentServer)] = self.serverConfig_myplexLocalToken
					accessToken = self.serverConfig_myplexLocalToken
				else:
					# this is the normal owner token
					#self.g_myplex_accessTokenDict[str(self.g_currentServer)] = self.serverConfig_myplexToken
					accessToken = self.serverConfig_myplexToken

		# now we genereate and store all headers that are needed
		self.setAccessTokenHeader(address=str(self.g_currentServer), accessToken=accessToken)

		printl("DreamPlex -> serverList is " + str(self.g_serverDict), self, "D")
		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getCurrentServer(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.g_currentServer

	#===========================================================================
	#
	#===========================================================================
	def setAccessTokenHeader(self, address, accessToken, serverVersion=None):
		printl("", self, "S")

		#if address not in self.g_myplex_accessTokenDict:
		self.g_myplex_accessTokenDict[address] = {}

		uToken = self.getAuthDetails({'token': accessToken})
		#printl("uToken: " +  str(uToken), self, "D", True, 6)
		self.g_myplex_accessTokenDict[address]["uToken"] = uToken

		hToken = self.getAuthDetails({'token': accessToken}, False)
		#printl("hToken: " +  str(hToken), self, "D", True, 6)
		self.g_myplex_accessTokenDict[address]["hToken"] = hToken

		aToken = self.getAuthDetails({'token': accessToken}, prefix="?")
		#printl("aToken: " +  str(aToken), self, "D", True, 6)
		self.g_myplex_accessTokenDict[address]["aToken"] = aToken

		# keep the bare token around for URL building (playback URLs are
		# fetched by the media player which cannot send headers)
		rawToken = accessToken
		if rawToken in (None, "", "None"):
			rawToken = None
		self.g_myplex_accessTokenDict[address]["rawToken"] = rawToken

		if serverVersion is not None:
			self.g_myplex_accessTokenDict[address]["serverVersion"] = serverVersion

		# we print the content of g_myplex_accesTokeDict later to not have it to often in logs

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def leaveOnError(self):
		printl("", self, "S")

		mainMenuList = []
		mainMenuList.append((_("Press exit to return"), "", "messageEntry"))
		mainMenuList.append((_("If you are using plex.tv"), "", "messageEntry"))
#		mainMenuList.append((_("please check if python-pyopenssl is installed."), "", "messageEntry"))
		mainMenuList.append((_("You can use Systemcheck in the menu."), "", "messageEntry"))

		printl("", self, "C")
		return mainMenuList

	#=============================================================================
	#
	#=============================================================================
	def loadSectionCache(self):
		printl("", self, "S")

		self.sectionCache = "%s%s.cache" % (config.plugins.dreamplex.cachefolderpath.value, "sections", )
		try:
			fd = open(self.sectionCache, "rb")
			self.g_sectionCache = pickle.load(fd)
			fd.close()
			printl("section chache data loaded", self, "D")
			self.sectionCacheLoaded = True
		except:
			printl("section chache data not loaded", self, "D")
			self.g_sectionCache = {}

		printl("", self, "C")

	#=============================================================================
	#
	#=============================================================================
	def saveSectionCache(self):
		printl("", self, "S")

		fd = open(self.sectionCache, "wb")
		pickle.dump(self.g_sectionCache, fd, 2)  # pickle.HIGHEST_PROTOCOL
		fd.close()

		printl("", self, "C")

	#=============================================================================
	#
	#=============================================================================
	def updateSectionCache(self, entryData):
		printl("", self, "S")

		myUuid = entryData.get('uuid', 'Unknown')
		updatedAt = entryData.get('updatedAt', 'Unknown')
		printl("uuid: " + str(myUuid), self, "D")
		printl("updatedAt: " + str(updatedAt), self, "D")
		source = "plex"

		try:
			if not self.sectionCacheLoaded:
				printl("adding data to section cache  ...", self, "D")
				self.g_sectionCache[myUuid] = {'updatedAt': updatedAt}
				self.g_sectionCache[myUuid]["source"] = "plex"

			elif self.sectionCacheLoaded and myUuid != "Unknown" and updatedAt != "Unknown":
				printl("searching in cache ...", self, "D")

				# check if uuid is in dict
				if myUuid in self.g_sectionCache:
					if int(self.g_sectionCache[myUuid].get("updatedAt")) == int(updatedAt):
						printl("unchanged data, using cache data ...", self, "D")
						self.g_sectionCache[myUuid]["source"] = "cache"
					else:
						printl("updating existing uuid in cache ...", self, "D")
						self.g_sectionCache[myUuid] = {'updatedAt': updatedAt}
						self.g_sectionCache[myUuid]["source"] = "plex"
				else:
					printl("new uuid found, updating cache ...", self, "D")
					self.g_sectionCache[myUuid] = {'updatedAt': updatedAt}
					self.g_sectionCache[myUuid]["source"] = "plex"
			else:
				printl("uuid or updateAt are unknown", self, "D")
		except Exception as e:
			printl("something went wrong with section cache", self, "D")
			printl("error: " + str(e), self, "D")

		printl("", self, "C")
		return source

	#=============================================================================
	#
	#=============================================================================
	def getAllSectionsXmlTree(self):
		printl("", self, "S")

		# get xml as tree
		if self.serverConfig_connectionType == "2":  # plex.tv

			if self.serverConfig_myplexToken == "ERROR":
				self.lastError = _("plex.tv Token error:\nCheck Username and Password.\n%s") % self.serverConfig_myplexToken
				return False
			else:
				tree = self.getXmlTreeFromPlex('/pms/system/library/sections')

		else:
			tree = self.getXmlTreeFromUrl(self.http + '://' + self.g_serverDict['address'] + '/library/sections')

		printl("", self, "C")
		return tree

	#===============================================================================
	#
	#===============================================================================
	def getSharedServerForPlexUser(self):
		printl("", self, "S")

		xmlResponse = self.getXmlTreeFromPlex('/pms/servers')

		printl("", self, "C")
		return xmlResponse

	#===============================================================================
	#
	#===============================================================================
	def getHomeUsersFromPlex(self):
		printl("", self, "S")

		xmlResponse = self.getXmlTreeFromPlex('/api/home/users')

		printl("", self, "C")
		return xmlResponse

	#===============================================================================
	#
	#===============================================================================
	def switchHomeUser(self, userId, pin):
		printl("", self, "S")

		xmlResponse = self.getXmlTreeFromPlex('/api/home/users/' + str(userId) + '/switch?pin=' + str(pin), requestType="POST")

		printl("", self, "C")
		return xmlResponse

	#===============================================================================
	#
	#===============================================================================
	def getPlexUserTokenForLocalServerAuthentication(self, ipInConfig):
		printl("", self, "S")

		printl("ipInConfig = " + str(ipInConfig), self, "D")
		xmlResponse = self.getSharedServerForPlexUser()

		servers = xmlResponse.findall('Server')

		for server in servers:
			entryData = (dict(server.items()))
			localAddresses = entryData["localAddresses"]
			if ipInConfig in localAddresses:
				printl("", self, "C")
				return entryData["accessToken"]

		printl("No ip match!!!!!!", self, "D")
		printl("", self, "C")
		return False

	#===============================================================================
	#
	#===============================================================================
	def getContentUrl(self, address, path):
		printl("", self, "S")

		contentUrl = '%s://%s%s' % (self.http, address, path)

		printl("contentUrl = " + contentUrl, self, "D")
		printl("", self, "C")
		return contentUrl

	#====================================================================
	#
	#====================================================================
	def getAuthDetails(self, details, url_format=True, prefix="&"):
		"""
		Takes the token and creates the required arguments to allow
		authentication.  This is really just a formatting tools
		@input: token as dict, style of output [opt] and prefix style [opt]
		@return: header string or header dict
		"""
		printl("", self, "S")

		token = details.get('token', None)
		printl("token: " + str(token), self, "D", True, 8)
		if url_format:
			if token is not None:
				printl("", self, "C")
				return prefix + "X-Plex-Token=" + str(token)
			else:
				printl("", self, "C")
				return ""
		else:
			if token is not None:
				printl("", self, "C")
				return {'X-Plex-Token': token}
			else:
				printl("", self, "C")
				return {}

	#============================================================================
	#
	#============================================================================
	def getNewMyPlexToken(self):
		"""
		Get a new plex.tv Token from plex.tv API
		@input: nothing
		@return: plex.tv token
		"""
		printl("", self, "S")

		printl("Getting new token", self, "I")

		# `(user or password) == ""` only caught an empty USERNAME: with a user
		# set and no password it evaluated the username, so we went on to send
		# Basic base64("user:") and plex.tv answered a confusing 401 "Invalid
		# email, username, or password". Check both, and say what is missing.
		if not self.g_myplex_username or not self.g_myplex_password:
			printl("Missing plex.tv credentials in config...", self, "D")
			self.lastResponse = _("plex.tv username or password missing in the server settings")

			printl("", self, "C")
			return False

		up = '%s:%s' % (self.g_myplex_username, self.g_myplex_password)
		base64string = b64encode(up.encode())
		if PY3:
			base64string = base64string.decode()

		myplex_header = getPlexHeader(self.g_sessionID)
		myplex_header['Authorization'] = "Basic %s" % base64string
		myplex_header['X-Plex-Username'] = self.g_myplex_username

		# same as getXmlTreeFromPlex: a plex.tv HTTPS failure (network or an
		# old box's OpenSSL) must not crash the login, just report no token
		try:
			conn = HTTPSConnection(PLEXTV_SERVER, timeout=20, port=443, context=ssl._create_unverified_context())
			conn.request(url="/users/sign_in.xml", method="POST", headers=myplex_header)
			data = conn.getresponse()
			response = data.read()
		except (ssl.SSLError, socket.error) as e:
			self.lastError = _("Could not reach plex.tv:\n%s") % str(e)
			printl("plex.tv sign_in failed: " + str(e), self, "W")
			printl("", self, "C")
			return False

		if not PY2:
			response = response.decode("UTF-8")

		try:
			xmlResult = etree.fromstring(response)
			entryData = (dict(xmlResult.items()))
			myId = entryData['id']
			token = entryData['authenticationToken']

		except Exception:
			token = None
			myId = None

		if token is None or myId is None:
			self.lastResponse = response

			printl("", self, "C")
			return False
		else:
			self.serverConfig_myplexToken = token
			self.serverConfig_myplexId = myId
			self.g_serverConfig.myplexTokenUsername.value = self.g_myplex_username
			self.g_serverConfig.myplexTokenUsername.save()
			self.g_serverConfig.myplexToken.value = self.serverConfig_myplexToken
			self.g_serverConfig.myplexToken.save()
			self.g_serverConfig.myplexId.value = self.serverConfig_myplexId
			self.g_serverConfig.myplexId.save()

		printl("token: " + token, self, "D", True, 8)
		printl("id: " + str(myId), self, "D")
		printl("", self, "C")
		return token

	#============================================================================
	#
	#============================================================================
	def getLastResponse(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.lastResponse

	#============================================================================
	#
	#============================================================================
	def doRequest(self, url, myType="GET", extraHeaders=None):
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		currentUrl = url
		redirectsLeft = 3
		server = self.getServerFromURL(currentUrl)

		try:
			while True:
				server = self.getServerFromURL(currentUrl)
				urlPath = self.getUrlPathFormURL(currentUrl)
				self.urlPath = urlPath

				if currentUrl.startswith("https"):
					# same trust model as getXmlTreeFromPlex: local boxes
					# have no CA store for the PMS certificate
					conn = HTTPSConnection(server, timeout=30, context=ssl._create_unverified_context())
				else:
					conn = HTTPConnection(server, timeout=30)

				# the very first time it is none
				# we also have to check if the server that where used changed meanwhile
				#if self.authHeader is None or server != self.lastHeaderForServer:

				authHeaderPartOne = self.get_hTokenForServer(server)
				#print("authHeaderPartOne " + str(authHeaderPartOne))
				self.lastHeaderForServer = server

				# if self.g_sessionID is None:
				# 	self.g_sessionID=str(uuid.uuid4())

				authHeaderPartTwo = getPlexHeader(self.g_sessionID)

				if authHeaderPartOne and authHeaderPartTwo:
					self.authHeader = dict(list(authHeaderPartOne.items()) + list(authHeaderPartTwo.items()))
				elif authHeaderPartTwo:
					self.authHeader = dict(list(authHeaderPartTwo.items()))
				else:
					self.authHeader = {}

				if extraHeaders:
					self.authHeader.update(extraHeaders)

				#printl("header: " + str(self.authHeader), self, "D")
				conn.request(myType, urlPath, headers=self.authHeader)

				data = conn.getresponse()
				status = int(data.status)

				if status in (301, 302, 303, 307, 308):
					location = data.getheader('Location')
					printl("status %d, following Location: %s" % (status, str(location)), self, "I")

					if not location or redirectsLeft <= 0:
						error = "HTTP redirect error: " + str(status) + " at " + str(currentUrl)
						printl(error, self, "D")
						self.lastError = error

						printl("", self, "C")
						return False

					redirectsLeft -= 1
					# Location may be absolute or relative
					currentUrl = urljoin(currentUrl, location)

					if status == 303:
						myType = "GET"

					continue

				elif status >= 400:
					error = "HTTP response error: " + str(data.status) + " " + str(data.reason)
					printl(error, self, "D")
					self.lastError = error

					printl("", self, "C")
					return False

				else:
					link = data.read()

					printl("", self, "C")
					return link

		except socket.gaierror:
			error = 'Unable to lookup host: ' + server + "\nCheck host name is correct"
			printl(error, self, "D")
			self.lastError = error

			printl("", self, "C")
			return False

		except socket.error as msg:
			error = "Unable to connect to " + server + "\nReason: " + str(msg)
			self.lastError = error
			printl(error, self, "D")

			printl("", self, "C")
			return False

		except Exception as ex:
			traceback.print_exc()
			printl("error: " + str(ex), self, "D")

	#========================================================================
	#
	#========================================================================
	def mediaType(self, partData, server):
		printl("", self, "S")
		stream = partData['key']
		myFile = encodeThat(partData['file'])
		self.fallback = False
		self.locations = ""

		# a new media starts here, and the transcode this may kick off has
		# to be filed under the same session as the playback itself
		self.g_playSessionID = newPlaybackId()
		printl("playback session: " + str(self.g_playSessionID), self, "D")

		#First determine what sort of 'file' file is
		printl("physical file location: " + str(myFile), self, "I")
		try:
			if myFile[0:2] == "\\\\":
				printl("Looks like a UNC", self, "I")
				myType = "UNC"
			elif myFile[0:1] == "/" or myFile[0:1] == "\\":
				printl("looks like a unix file", self, "I")
				myType = "unixfile"
			elif myFile[1:3] == ":\\" or myFile[1:2] == ":/":
				printl("looks like a windows file", self, "I")
				myType = "winfile"
			else:
				printl("uknown file type", self, "I")
				printl("file = " + str(myFile), self, "I")
				myType = "notsure"
		except Exception:
				printl("uknown file type", self, "I")
				printl("file = " + str(myFile), self, "I")
				myType = "notsure"

		self.currentFile = myFile
		self.currentType = myType

		# 0 is linux local mount override
		if self.g_stream == "0":
			#check if the file can be found locally
			if myType == "unixfile" or myType == "winfile" or myType == "UNC":

				tree = getXmlContent(config.plugins.dreamplex.configfolderpath.value + "mountMappings")

				self.serverID = str(self.g_serverConfig.id.value)
				printl("serverID: " + str(self.serverID), self, "D")

				if tree:
					for entry in tree.findall("server"):
						printl("servername: " + str(entry.get('id')), self, "D")
						if str(entry.get('id')) == str(self.serverID):

							for mapping in entry.findall('mapping'):
								self.lastMappingId = mapping.attrib.get("id")
								remotePathPart = mapping.attrib.get("remotePathPart")
								localPathPart = mapping.attrib.get("localPathPart")
								printl("self.lastMappingId: " + str(self.lastMappingId), self, "D")
								printl("remotePathPart: " + str(remotePathPart), self, "D")
								printl("localPathPart: " + str(localPathPart), self, "D")

								locationCheck = self.checkFileLocation(remotePathPart, localPathPart)

								# if we find the media within the provided location we leave
								if locationCheck:
									return locationCheck

				printl("Sorry I didn't find the file on the provided locations", self, "I")

			self.fallback = True
			printl("No local mount override possible ... switching to transcoded mode", self, "I")

			self.g_stream = "1"

		# 1 is stream no matter what
		if self.g_stream == "1":
			printl("Selecting stream", self, "I")
			printl("", self, "C")
			return "%s://%s%s" % (self.http, server, stream)

		# 2 is use SMB or afp override
		elif self.g_stream == "2":
			if self.g_stream == "2":
				protocol = "smb"
			else:
				protocol = "afp"

			printl("Selecting smb/unc")
			if myType == "UNC":
				filelocation = protocol + ":" + myFile.replace("\\", "/")
			else:
				#Might be OSX type, in which case, remove Volumes and replace with server
				server = server.split(':')[0]
				loginstring = ""

				if self.g_nasoverride == "true":
					if not self.g_nasoverrideip == "":
						server = self.g_nasoverrideip
						printl("Overriding server with: " + server, self, "I")

					nasuser = self.g_nasuserid
					if not nasuser == "":
						loginstring = self.g_nasuserid + ":" + self.g_naspass + "@"
						printl("Adding AFP/SMB login info for user " + nasuser, self, "I")

				if myFile.find('Volumes') > 0:
					filelocation = protocol + ":/" + myFile.replace("Volumes", loginstring + server)
				else:
					if myType == "winfile":
						filelocation = protocol + "://" + loginstring + server + "/" + myFile[3:]
					else:
						#else assume its a file local to server available over smb/samba (now we have linux PMS).  Add server name to file path.
						filelocation = protocol + "://" + loginstring + server + myFile

			if self.g_nasoverride == "true" and self.g_nasroot != "":
				#Re-root the file path
				printl("Altering path " + filelocation + " so root is: " + self.g_nasroot, self, "I")
				if '/' + self.g_nasroot + '/' in filelocation:
					components = filelocation.split('/')
					index = components.index(self.g_nasroot)
					for i in range(3, index):
						components.pop(3)
					filelocation = '/'.join(components)
		else:
			printl("No option detected, streaming is safest to choose", self, "I")
			filelocation = "%s://%s%s" % (self.http, server, stream)

		printl("Returning URL: " + filelocation, self, "I")
		printl("", self, "C")
		return filelocation

	#===========================================================================
	#
	#===========================================================================

	def checkFileLocation(self, remotePathPart, localPathPart):
		printl("", self, "S")

		printl("Checking for local file", self, "I")

		printl("untouched remotePathPart: " + str(remotePathPart), self, "D")

		if self.currentType == "winfile" or self.currentType == "UNC":
			# to prevent wrong configuration errors we change all slashes to backslahes
			# this is nessesarry if the users enters the path with slashes instead fo backslahes
			remotePathPart.replace("/", "\\")

		printl("remotePathPart: " + str(remotePathPart), self, "D")
		printl("localPathPart: " + str(localPathPart), self, "D")

		myFile = self.currentFile
		printl("original file string: " + str(myFile), self, "D")

		myFile = myFile.replace(remotePathPart, localPathPart)

		# now we change backslahes back to slahes
		if self.currentType == "winfile" or self.currentType == "UNC":
			myFile = myFile.replace("\\", "/")

		myFile = unquote(myFile)

		# for some reason there might be double // in the string we remove them
		myFile = myFile.replace("//", "/")

		printl("altered file string: " + str(myFile), self, "I")
		try:
			exists = open(myFile)
			printl("Local file found, will use this", self, "I")
			exists.close()

			printl("", self, "C")
			return "file:" + myFile
		except:
			self.locations += str(myFile) + "\n"
			printl("", self, "C")
			return False

	#===========================================================================
	#
	#===========================================================================
	def getStreamDataById(self, server, myId, loadExtraData=False):
		printl("", self, "S")

		printl("Gather media stream info", self, "I")

		#get metadata for audio and subtitle
		suburl = "%s://%s/library/metadata/%s" % (self.http, server, myId)

		if loadExtraData:
			suburl += "?checkFiles=1&includeExtras=1&includeRelated=1&includeRelatedCount=0"

		self.g_currentServer = server
		printl("g_currentServer: " + str(self.g_currentServer), self, "D")

		html = self.doRequest(suburl)
		printl("retrived html: " + str(html), self, "D")

		tree = None

		try:
			tree = etree.fromstring(html)
		except Exception as e:
			printl("Exception: " + str(e), self, "D")
			self.lastResponse = str(html)

		printl("", self, "C")
		return tree

	#===========================================================================
	#
	#===========================================================================
	def getSelectedSubtitleDataById(self, server, myId, forcedOnly=False):  # mh : added forcedOnly param
		printl("", self, "S")
		printl("server +  myId: " + str(server) + " / " + str(myId), self, "D")

		tree = self.getStreamDataById(server, myId)
		if tree == None:
			printl("error getStreamDataById is None", self, "D")
			return {}

		fromParts = tree.getiterator('Part') if PY2 else tree.iter('Part')
		partitem = None
		#Get the Parts info for media type and source selection
		for part in fromParts:
			try:
				partitem = part.get('id'), part.get('file')
			except:
				pass

		tags = tree.getiterator('Stream') if PY2 else tree.iter('Stream')

		printl("Part Item: " + str(partitem), self, "I")

		selectedSubtitle = {'id': -1,
							'index': -1,
							'language': "Disabled",
							'languageCode': "NA",
							'format': "Disabled",
							'partid': partitem[0]
							}
		for bits in tags:
			stream = dict(bits.items())
			printl("mh: stream=" + str(stream), self, "D")

			selected = stream.get('selected', "")
			default = stream.get('default', "")

			if stream['streamType'] == '3' and (selected == '1' or default == '1'):  # subtitle #mh: treat default same as selected
				try:
					index = stream.get('index', "-1")
					#mh : handle forced only
					reject = False
					if forcedOnly:
						streamForced = stream.get('forced', "")
						printl("mh: streamForced=" + str(streamForced), self, "D")
						if streamForced != '1':
							reject = True
					if reject:
						printl("mh: subtitle rejected as not forced", self, "D")
					else:
					#
						selectedSubtitle = {'id': stream['id'],
									'index': index,
									'language': stream['language'],
									'languageCode': stream['languageCode'],
									'format': stream['format'],
									'partid': partitem[0]
							}
						printl("selectedSubtitle = " + str(selectedSubtitle), self, "D")
				except:
					printl("Unable to read subtitles due to XML parsing error", self, "E")

		printl("", self, "C")
		return selectedSubtitle

	#===========================================================================
	#
	#===========================================================================
	def getSubtitlesById(self, server, myId):
		"""
		sample:
		<Stream id="25819" streamType="3" selected="1" default="1" index="4" language="Deutsch" languageCode="ger" format="srt"/>
		<Stream id="25820" streamType="3" index="5" language="English" languageCode="eng" format="srt"/>
		"""
		printl("", self, "S")

		subtitlesList = []

		tree = self.getStreamDataById(server, myId)
		if tree == None:
			printl("error getStreamDataById is None", self, "D")
			return {}

		fromParts = tree.getiterator('Part') if PY2 else tree.iter('Part')
		partitem = None
		#Get the Parts info for media type and source selection
		for part in fromParts:
			try:
				partitem = part.get('id'), part.get('file')
			except:
				pass

		tags = tree.getiterator('Stream') if PY2 else tree.iter('Stream')

		subtitle = {'id': 0,
		                'language': "None",
						'partid': partitem[0],
		                'forced': False
					}

		subtitlesList.append(subtitle)
		for bits in tags:
			stream = dict(bits.items())
			if stream['streamType'] == '3':  # subtitle
				# <Stream id="217871" streamType="3" selected="1" default="1" forced="1" codec="srt" index="2" language="Deutsch" languageCode="ger" codecID="S_TEXT/UTF8" format="srt" title="" />
				# <Stream id="217865" key="/library/streams/217865" streamType="3" selected="1" codec="srt" format="srt" />

				try:
					subtitleId = stream['id']
					myFormat = stream['format']
					partid = partitem[0]

					codec = stream.get('codec', None)
					selected = stream.get('selected', False)
					language = stream.get('language', 'unbekannt')
					languageCode = stream.get('languageCode', 'Unknown')
					index = stream.get('index', None)
					default = stream.get('default', False)

					forced = stream.get('forced', False)
					if forced == "1":
						forced = True

					subtitle = {'id': subtitleId,
										'index': index,
										'language': language,
										'languageCode': languageCode,
										'myFormat': myFormat,
										'partid': partid,
										'selected': selected,
										'codec': codec,
										'default': default,
										'forced': forced
								}

					printl("subtitle = " + str(subtitle), self, "D")

					subtitlesList.append(subtitle)
				except:
					printl("Unable to set subtitles due to XML parsing error", self, "E")
					pass

		printl("subtitlesList = " + str(subtitlesList), self, "D")

		printl("", self, "C")
		return subtitlesList

	#===========================================================================
	#
	#===========================================================================
	def getAudioById(self, server, myId):
		"""
		sample:
		<Stream id="25819" streamType="3" selected="1" default="1" index="4" language="Deutsch" languageCode="ger" format="srt"/>
		<Stream id="25820" streamType="3" index="5" language="English" languageCode="eng" format="srt"/>
		"""
		printl("", self, "S")

		audioList = []

		tree = self.getStreamDataById(server, myId)
		if tree == None:
			printl("error getStreamDataById is None", self, "D")
			return []

		fromParts = tree.getiterator('Part') if PY2 else tree.iter('Part')
		partitem = None
		#Get the Parts info for media type and source selection
		for part in fromParts:
			try:
				partitem = part.get('id'), part.get('file')
			except:
				pass

		tags = tree.getiterator('Stream') if PY2 else tree.iter('Stream')

		for bits in tags:
			stream = dict(bits.items())
			if stream['streamType'] == '2':  # audio
				try:
					audio = {'id': stream.get('id', -1),
										'index': stream.get('index', -1),
										'language': stream.get('language', 'Unknown'),
										'languageCode': stream.get('languageCode', 'Ukn'),
										'format': stream.get('format', 'UKN'),
										'partid': partitem[0],
										'selected': stream.get('selected', 0)
								}

					audioList.append(audio)
				except:
					printl("Unable to set audio due to XML parsing error", self, "E")
					pass

		printl("audioList = " + str(audioList), self, "D")

		printl("", self, "C")
		return audioList

	#===========================================================================
	#
	#===========================================================================
	def setSubtitleById(self, server, sub_id, part_id):
		printl("", self, "S")

		url = "%s://%s/library/parts/%s?subtitleStreamID=%s" % (self.http, str(server), str(part_id), str(sub_id))

		#mh : detect if subtitle none has been selectd
		self.g_setSubtitleById_None = (sub_id == 0)
		printl("mh: sub_id=" + str(sub_id), self, "D")
		printl("mh: g_setSubtitleById_None=" + str(self.g_setSubtitleById_None), self, "D")

		self.doRequest(url, myType="PUT")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def setAudioById(self, server, audio_id, part_id):
		printl("", self, "S")

		url = "%s://%s/library/parts/%s?audioStreamID=%s" % (self.http, str(server), str(part_id), str(audio_id))

		self.doRequest(url, myType="PUT")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getExtraData(self, server, myId, myType, loadExtraData):
		"""
		Cycle through the Parts sections to find all "selected" audio and subtitle streams
		If a stream is marked as selected=1 then we will record it in the dict
		Any that are not, are ignored as we do not need to set them
		We also record the media locations for playback decision later on
		"""
		printl("", self, "S")

		tree = self.getStreamDataById(server, myId, loadExtraData)

		parts = []
		partsCount = 0
		subtitle = {}
		subCount = 0
		audio = {}
		audioCount = 0
		external = {}
		videoData = {}
		mediaData = {}
		subOffset = -1
		audioOffset = -1
		selectedSubOffset = -1
		selectedAudioOffset = -1

		if not tree:
			return {}
		else:
			fromVideo = tree.find(myType)  # Track or Video

			videoData['title'] = fromVideo.get('title', "")
			videoData['tagline'] = fromVideo.get('tagline', "")
			videoData['summary'] = fromVideo.get('summary', "")
			videoData['year'] = fromVideo.get('year', "")
			videoData['studio'] = fromVideo.get('studio', "")
			videoData['viewOffset'] = fromVideo.get('viewOffset', 0)
			videoData['duration'] = fromVideo.get('duration', 0)
			videoData['contentRating'] = fromVideo.get('contentRating', "")

			mediaData['audioCodec'] = fromVideo.get('audioCodec', "")
			mediaData['videoCodec'] = fromVideo.get('videoCodec', "")
			mediaData['videoResolution'] = fromVideo.get('videoResolution', "")
			mediaData['videoFrameRate'] = fromVideo.get('videoFrameRate', "")

			contents = "type"

			if loadExtraData:
				try:
					extraContent = tree.find('Video/Extras')  # extra content
					for video in extraContent.findall("Video"):
						for media in video.findall("Media"):
							for part in media.findall("Part"):
								try:
									bits = part.get('key'), video.get("type") + ": " + video.get("title") + " (" + media.get("width") + "x" + media.get("height") + ")", part.get('container'), video.get("type"), video.get("duration")
									parts.append(bits)
									partsCount += 1
								except:
									pass
				except Exception:
					pass
			else:
				mainContent = tree.find('Video/Media')  # main content
				#Get the Parts info for media type and source selection
				for part in mainContent.findall("Part"):
					printl("part.attrib: " + str(part.attrib), self, "D")

					try:
						bits = part.get('key'), part.get('file'), part.get('container'), part.get('size'), part.get('duration')
						parts.append(bits)
						partsCount += 1
					except:
						pass

					if myType == "Video":
						if self.g_streamControl == "1" or self.g_streamControl == "2":

							contents = "all"
							fromStream = part.getiterator('Stream') if PY2 else part.iter('Stream')
							printl("fromStream: " + str(fromStream), self, "D")
							#streamType: The type of media stream/track it is (1 = video, 2 = audio, 3 = subtitle)

							for bits in fromStream:
								printl("bits.attrib: " + str(bits.attrib), self, "D")
								stream = dict(bits.items())
								printl("stream: " + str(stream), self, "D")
								if stream['streamType'] == '2':  # audio
									audioCount += 1
									audioOffset += 1
									try:
										if stream['selected'] == "1":
											printl("Found preferred audio id: " + str(stream['id']), self, "I")
											audio = stream
											selectedAudioOffset = audioOffset
									except:
										pass

								elif stream['streamType'] == '3':  # subtitle
									subOffset += 1
									try:
										if stream['key']:
											printl("Found external subtitles id : " + str(stream['id']), self, "I")
											external = stream
											external['key'] = "%s://%s%s" % (self.http, server, external['key'])
									except:
										#Otherwise it's probably embedded
										try:
											if stream['selected'] == "1":
												printl("Found preferred subtitles id : " + str(stream['id']), self, "I")
												subCount += 1
												subtitle = stream
												selectedSubOffset = subOffset
										except:
											pass
						else:
								printl("Stream selection is set OFF", self, "I")

			streamData = {'contents': contents,
						'audio': audio,
						'audioCount': audioCount,
						'subtitle': subtitle,
						'subCount': subCount,
						'external': external,
						'parts': parts,
						'partsCount': partsCount,
						'videoData': videoData,
						'mediaData': mediaData,
						'subOffset': selectedSubOffset,
						'audioOffset': selectedAudioOffset}

			printl("streamData = " + str(streamData), self, "D")
			printl("", self, "C")
			return streamData

		#===========================================================================
	#
	#===========================================================================
	def getAudioSubtitlesMedia(self, server, myId, myType, loadExtraData):
		"""
		Cycle through the Parts sections to find all "selected" audio and subtitle streams
		If a stream is marked as selected=1 then we will record it in the dict
		Any that are not, are ignored as we do not need to set them
		We also record the media locations for playback decision later on
		"""
		printl("", self, "S")

		tree = self.getStreamDataById(server, myId, loadExtraData)

		parts = []
		partsCount = 0
		contents = ""
		subtitle = {}
		subCount = 0
		audio = {}
		audioCount = 0
		external = {}
		videoData = {}
		mediaData = {}
		subOffset = -1
		audioOffset = -1
		selectedSubOffset = -1
		selectedAudioOffset = -1

		streamData = {'contents': contents,
					'audio': audio,
					'audioCount': audioCount,
					'subtitle': subtitle,
					'subCount': subCount,
					'external': external,
					'parts': parts,
					'partsCount': partsCount,
					'videoData': videoData,
					'mediaData': mediaData,
					'subOffset': selectedSubOffset,
					'audioOffset': selectedAudioOffset}

		self.g_SelectedEmbeddedSubtitleData = None  # mh

		if not tree:
			return streamData
		else:
			fromVideo = tree.find(myType)  # Track or Video

			videoData['title'] = fromVideo.get('title', "")
			videoData['tagline'] = fromVideo.get('tagline', "")
			videoData['summary'] = fromVideo.get('summary', "")
			videoData['year'] = fromVideo.get('year', "")
			videoData['studio'] = fromVideo.get('studio', "")
			videoData['viewOffset'] = fromVideo.get('viewOffset', 0)
			videoData['duration'] = fromVideo.get('duration', 0)
			videoData['contentRating'] = fromVideo.get('contentRating', "")

			mediaData['audioCodec'] = fromVideo.get('audioCodec', "")
			mediaData['videoCodec'] = fromVideo.get('videoCodec', "")
			mediaData['videoResolution'] = fromVideo.get('videoResolution', "")
			mediaData['videoFrameRate'] = fromVideo.get('videoFrameRate', "")

			contents = "type"

			partId = -1  # mh

			if loadExtraData:
				extraContent = tree.find(myType + '/Extras')  # extra content
				if extraContent is not None:
					for video in extraContent.findall("Video"):
						for media in video.findall("Media"):
							for part in media.findall("Part"):
								try:
									# cloud extras have no width/height, keep them anyway
									label = str(video.get("type", "extra")) + ": " + str(video.get("title", ""))
									if media.get("width") and media.get("height"):
										label += " (" + media.get("width") + "x" + media.get("height") + ")"
									bits = (part.get('key'), label, part.get('container'),
										video.get("type"), video.get("duration"), video.get("ratingKey"))
									parts.append(bits)
									partsCount += 1
								except Exception as e:
									printl("skipping unparseable extra: " + str(e), self, "D")

				# modern PMS references the main trailer via primaryExtraKey;
				# resolve it when the Extras subtree gave nothing playable
				if partsCount == 0:
					primaryExtraKey = fromVideo.get('primaryExtraKey')
					if primaryExtraKey:
						extraId = str(primaryExtraKey).rstrip('/').split('/')[-1]
						extraTree = self.getStreamDataById(server, extraId)
						try:
							extraVideo = extraTree.find('Video')
							extraPart = extraTree.find('Video/Media/Part')
							bits = (extraPart.get('key'),
								str(extraVideo.get('type', 'trailer')) + ": " + str(extraVideo.get('title', '')),
								extraPart.get('container'), extraVideo.get('type', 'clip'),
								extraVideo.get('duration'), extraVideo.get('ratingKey', extraId))
							parts.append(bits)
							partsCount += 1
						except Exception as e:
							printl("primaryExtraKey not playable: " + str(e), self, "W")
			else:
				# every <Media> child is a playable VERSION of the item (e.g.
				# 1080p and 4K); collect the parts of all of them so the
				# player can offer a choice - upstream only read the first one
				versionedParts = []
				for mediaIndex, media in enumerate(tree.findall(myType + '/Media')):
					for part in media.findall("Part"):
						versionedParts.append((mediaIndex, media, part))

				#Get the Parts info for media type and source selection
				for mediaIndex, media, part in versionedParts:
					printl("part.attrib: " + str(part.attrib), self, "D")

					partId = part.attrib['id']  # mh

					try:
						# indexes 0-4 are consumed by DP_Player/mediaType;
						# 5-6 label the version in the selection dialog,
						# 7 is the mediaIndex for the universal transcoder and
						# 8 the HDR kind ("" for SDR), which labels it too
						bits = (part.get('key'), part.get('file'), part.get('container'),
							part.get('size'), part.get('duration'),
							media.get('videoResolution'), media.get('videoCodec'),
							mediaIndex, videoRangeOfPart(part))
						parts.append(bits)
						partsCount += 1
					except Exception as e:
						printl("Error: " + str(e), self, "D")

					# audio/subtitle stream preselection keeps reading only the
					# first version, exactly like before
					if myType == "Video" and mediaIndex == 0:
						if self.g_streamControl == "1" or self.g_streamControl == "2":

							contents = "all"
							fromStream = part.getiterator('Stream') if PY2 else part.iter('Stream')
							printl("fromStream: " + str(fromStream), self, "D")
							#streamType: The type of media stream/track it is (1 = video, 2 = audio, 3 = subtitle)

							for bits in fromStream:
								printl("bits.attrib: " + str(bits.attrib), self, "D")
								stream = dict(bits.items())
								printl("stream: " + str(stream), self, "D")
								if stream['streamType'] == '2':  # audio
									audioCount += 1
									audioOffset += 1
									try:
										if stream['selected'] == "1":
											printl("Found preferred audio id: " + str(stream['id']), self, "I")
											audio = stream
											selectedAudioOffset = audioOffset
									except Exception as e:
										printl("Error: " + str(e), self, "D")

								elif stream['streamType'] == '3':  # subtitle
									subOffset += 1
									try:
										if stream['key']:
											printl("Found external subtitles id : " + str(stream['id']), self, "I")
											external = stream
											external['key'] = "%s://%s%s" % (self.http, server, external['key'])
									except Exception as e:
										printl("Error: " + str(e) + " maybe we are embedded?", self, "D")
										try:
											if stream['selected'] == "1":
												printl("Found preferred subtitles id : " + str(stream['id']), self, "I")
												subCount += 1
												subtitle = stream
												selectedSubOffset = subOffset
										except Exception as e:
											printl("even not embedded ...: " + str(e), self, "D")

											#mh : try 'default' instead
											try:
												if stream['default'] == "1":
													printl("Found default subtitles id : " + str(stream['id']), self, "I")
													subCount += 1
													subtitle = stream
													selectedSubOffset = subOffset
											except Exception as e:
												printl("even not embedded (2)...: " + str(e), self, "D")

											if selectedSubOffset == subOffset:
												try:
													self.selectedSubtitle = {'id': stream['id'],
																		'index': stream['index'],
																		'language': stream['language'],
																		'languageCode': stream['languageCode'],
																		'format': stream['codec'],
																		'partid': partId
																		}
													printl("mh: default selectedSubtitle=" + str(self.selectedSubtitle), self, "D")

													printl("mh: stream.forced=" + str(stream['forced']), self, "D")
													printl("mh: g_serverConfig.useForcedSubtitles=" + str(self.g_serverConfig.useForcedSubtitles.value), self, "D")

													if self.g_serverConfig.useForcedSubtitles.value:
														if stream['forced'] == '1':
															printl("mh: setting forced g_SelectedEmbeddedSubtitleData", self, "D")
															self.g_SelectedEmbeddedSubtitleData = self.selectedSubtitle

												except Exception as e:
													printl("mh: error setting selectedSubtitle: " + str(e), self, "D")

						else:
								printl("Stream selection is set OFF", self, "I")

			streamData = {'contents': contents,
						'audio': audio,
						'audioCount': audioCount,
						'subtitle': subtitle,
						'subCount': subCount,
						'external': external,
						'parts': parts,
						'partsCount': partsCount,
						'videoData': videoData,
						'mediaData': mediaData,
						'subOffset': selectedSubOffset,
						'audioOffset': selectedAudioOffset}

			printl("streamData = " + str(streamData), self, "D")
			printl("", self, "C")
			return streamData

	#========================================================================
	# mh
	#========================================================================

	def getSelectedEmbeddedSubtitleData(self):
		return self.g_SelectedEmbeddedSubtitleData

	#========================================================================
	#
	#========================================================================

	def setSelectedVersion(self, mediaIndex):
		printl("selected version mediaIndex: " + str(mediaIndex), self, "D")
		self.g_selectedMediaIndex = mediaIndex

	#========================================================================
	#
	#========================================================================
	def getMediaOptionsToPlay(self, myId, vids, override=False, myType="Video", loadExtraData=False):
		printl("", self, "S")
		self.g_selectedMediaIndex = None  # a new item starts unselected

		self.getTranscodeSettings(override)
		self.server = self.getServerFromURL(vids)
		self.streams = self.getAudioSubtitlesMedia(self.server, myId, myType, loadExtraData)

		parts = self.streams['parts']
		if not loadExtraData and len(parts) > 1:
			ranges = [part[8] if len(part) > 8 else "" for part in parts]
			if any(ranges) and not all(ranges) and not boxSupportsHdr():
				# a box without HDR cannot show an HDR version right (black,
				# when the server does not tone-map), and the dialog opens on
				# the first entry: SDR first. The choice still travels by each
				# version's own mediaIndex ([7]), not by its place in this list
				parts.sort(key=lambda part: 1 if (len(part) > 8 and part[8]) else 0)

		printl("partsCount: " + str(self.streams['partsCount']), self, "D")
		printl("parts: " + str(self.streams['parts']), self, "D")
		printl("server: " + str(self.streams), self, "D")

		printl("", self, "C")
		return self.streams['partsCount'], self.streams['parts'], self.server

	#========================================================================
	#
	#========================================================================
	def playLibraryMedia(self, myId, url, isExtraData=False):
		printl("", self, "S")

		printl("playLibraryMediaUrl: " + str(url), self, "D")

		printl("server: " + str(self.server), self, "D")

		if url is None:
			return

		# normally mediaType() already opened one for this media
		if not self.g_playSessionID:
			self.g_playSessionID = newPlaybackId()

		protocol = url.split(':', 1)[0]

		# set standard playurl
		playurl = url

		foundForcedSubs = False
		subtitleFileTemp = None

		#alter playurl if needed
		if protocol == "file":
			printl("We are playing a local file", self, "D")
			playurl = url.split(':', 1)[1]

			if self.g_serverConfig.srtRenamingForDirectLocal.value:
				myFile = url.split('/')[-1]
				myFileWoExtension = myFile[:-4]
				extension = myFile[-3:]
				path = playurl[:-len(myFile)]
				language = self.g_serverConfig.subtitlesLanguage.value

				printl("path " + str(path), self, "D")
				printl("myFileWoExtension " + str(myFileWoExtension), self, "D")
				printl("extension " + str(extension), self, "D")
				printl("myFile " + str(myFile), self, "D")

				if self.g_setSubtitleById_None == True:
					printl("mh: skipping external forced subs check becase g_setSubtitleById_None=" + str(self.g_setSubtitleById_None), self, "D")
				else:
					#mh: look for forced subs
					subtitleFileOrig = path + myFileWoExtension + "." + language + ".forced.srt"
					foundForcedSubs = fileExists(subtitleFileOrig)
					printl("mh: external foundForcedSubs=" + str(foundForcedSubs), self, "D")
					if not foundForcedSubs:
					#
						subtitleFileOrig = path + myFileWoExtension + "." + language + ".srt"

					#check if there is a srt file with specific language
					if fileExists(subtitleFileOrig):

						subtitleFileTemp = path + myFileWoExtension + ".srt"
						if foundForcedSubs:
							printl("copying forced srt to subtitleFileTemp " + str(subtitleFileTemp), self, "D")
							copyfile(subtitleFileOrig, subtitleFileTemp)
						else:
							printl("copying srt to subtitleFileTemp " + str(subtitleFileTemp), self, "D")
							copyfile(subtitleFileOrig, subtitleFileTemp)
					else:
						printl("unable to find the following subtitle file ... " + str(subtitleFileOrig), self, "D")

		elif protocol == "http":
			printl("We are playing a stream", self, "I")
			if self.g_transcode == "true":
				printl("We will be transcoding the stream", self, "I")
				playurl = self.transcode(myId, url)
			else:
				printl("We will be playing raw stream", self, "I")
				# token as URL parameter, and never crash on a missing one
				playurl = self.appendTokenToUrl(url, self.server)

		try:
			resume = int(int(self.streams['videoData']['viewOffset']))
		except:
			resume = 0

		printl("Resume has been set to " + str(resume), self, "I")

		result = 1

		if resume > 0:

			if result == -1:
				printl("", self, "C")
				return

		if not (self.g_transcode == "true"):
			self.setAudioSubtitles(self.streams)

		# multiuser works only if the server is compatible
		self.setServerDetails()

		printl("multiUserServer (version): " + str(self.g_multiUser) + "(" + self.g_serverVersion + ")", self, "D")

		printl("PLAYURL => " + playurl, self, "I")
		printl("RESUME => " + str(resume), self, "I")
		printl("", self, "C")

		printl("mh: isExtraData=" + str(isExtraData), self, "D")

		# local files never touch the server, so they get no session
		if protocol != "file":
			playurl = self.appendSessionToUrl(playurl)

		playerData = {}
		playerData["playUrl"] = playurl
		playerData["resumeStamp"] = resume
		playerData["server"] = self.server
		playerData["id"] = myId
		playerData["playSessionID"] = self.g_playSessionID
		playerData["multiUserServer"] = self.g_multiUser
		playerData["playbackType"] = self.serverConfig_playbackType
		playerData["connectionType"] = self.serverConfig_connectionType
		playerData["localAuth"] = self.serverConfig_localAuth
		playerData["transcodingSession"] = self.g_playSessionID or self.g_sessionID
		playerData["videoData"] = self.streams['videoData']
		playerData["mediaData"] = self.streams['mediaData']

		playerData["usingExtForcedSubs"] = False

		if not isExtraData:
			playerData["fallback"] = self.fallback
			playerData["locations"] = self.locations
			playerData["currentFile"] = self.currentFile
			playerData["subtitleFileTemp"] = subtitleFileTemp

			printl("mh: foundForcedSubs=" + str(foundForcedSubs), self, "D")
			if foundForcedSubs:
				printl("mh: using found forced temp subtitle file: ", str(subtitleFileTemp), self, "D")
				playerData["subtitleFileTemp"] = subtitleFileTemp
				playerData["usingExtForcedSubs"] = True
			elif subtitleFileTemp != None:
				printl("mh: using found temp subtitle file", self, "D")
				playerData["subtitleFileTemp"] = subtitleFileTemp
			printl("mh: subtitleFileTemp=" + str(subtitleFileTemp), self, "D")

		playerData["universalTranscoder"] = self.g_serverConfig.universalTranscoder.value

		printl("mh: playerData=" + str(playerData), self, "D")

		return playerData

	#===========================================================================
	#
	#===========================================================================
	def setAudioSubtitles(self, stream):
		printl("", self, "S")

		#mh : DO NOT UNDERSTAND!!! this function claims to set stuff but seems to do fuck all other than trace claims that it does!

		if stream['contents'] == "type":
			printl("No streams to process.", self, "I")

			if self.g_streamControl == "3":
				printl("All subs disabled", self, "I")

			printl("", self, "C")
			return True

		if self.g_streamControl == "1" or self.g_streamControl == "2":
			audio = stream['audio']
			printl("Attempting to set Audio Stream", self, "I")
			#Audio Stream first
			if stream['audioCount'] == 1:
				printl("Only one audio stream present - will leave as default", self, "I")
			elif stream['audioCount'] > 1:
				printl("Multiple audio stream. Attempting to set to local language", self, "I")
				try:
					if audio['selected'] == "1":
						printl("Found preferred language at index " + str(stream['audioOffset']), self, "I")
						printl("Audio set", self, "I")
				except:
					pass

		#Try and set embedded subtitles
		if self.g_streamControl == "1":
			subtitle = stream['subtitle']
			printl("Attempting to set subtitle Stream", self, "I")
			try:
				if stream['subCount'] > 0 and subtitle['languageCode']:
					printl("Found embedded subtitle for local language", self, "I")
					printl("Enabling embedded subtitles", self, "I")
					printl("", self, "C")
					return True
				else:
					printl("No embedded subtitles to set", self, "I")
			except:
				printl("Unable to set subtitles", self, "I")

		if self.g_streamControl == "1" or self.g_streamControl == "2":
			external = stream['external']
			printl("Attempting to set external subtitle stream", self, "I")

			try:
				if external:
					printl("mh: external=" + str(external), self, "D")

					try:
						printl("External of type [" + external['codec'] + "]", self, "I")
						if external['codec'] == "idx" or external['codec'] == "sub":
							#printl("mh: 111", self , "D")
							printl("Skipping IDX/SUB pair - not supported yet", self, "I")
						else:
							#printl("mh: 222", self , "D")
							printl("mh: setting external", self, "D")
							printl("", self, "C")
							return True
					except:
						#printl("mh: 333", self , "D")
						pass
				else:
					printl("No external subtitles available. Will turn off subs", self, "I")
			except:
				printl("No External subs to set", self, "I")

		printl("", self, "C")
		return False

	#===============================================================================
	#
	#===============================================================================
	def getXmlTreeFromPlex(self, url, requestType="GET"):
		"""
		Connect to the my.plexapp.com service and get an XML pages
		A seperate function is required as interfacing into plex.tv
		is slightly different than getting a standard URL
		@input: url to get, whether we need a new token, whether to display on screen err
		@return: an xml page as string or false
		"""
		printl("", self, "S")
		printl("url = " + PLEXTV_SERVER + url, self, "D")
		#
		myplex_header = getPlexHeader(self.g_sessionID)
		myplex_header['X-Plex-Token'] = str(self.serverConfig_myplexToken)

		# talking to plex.tv over HTTPS can fail or be flaky: plex.tv is a
		# round-robin of AWS IPs and some may be unreachable from a given
		# network. A short per-attempt timeout keeps the UI responsive when
		# plex.tv is down (HTTPSConnection already tries every resolved IP
		# within one attempt, so a single retry is enough for a transient
		# hiccup); never let a failure crash the plugin - report it instead.
		response = None
		lastException = None
		for attempt in range(2):
			try:
				conn = HTTPSConnection(PLEXTV_SERVER, timeout=8, port=443, context=ssl._create_unverified_context())
				conn.request(url=url, method=requestType, headers=myplex_header)
				data = conn.getresponse()
				response = data.read()
				break
			except (ssl.SSLError, socket.error) as e:
				lastException = e
				printl("plex.tv attempt %d failed: %s" % (attempt + 1, str(e)), self, "W")
				try:
					conn.close()
				except Exception:
					pass
			except Exception as e:
				lastException = e
				printl("plex.tv unexpected error: " + str(e), self, "W")
				break

		if response is None:
			self.lastError = _("Could not reach plex.tv:\n%s\n\nTip: use an IP connection with an Access Token instead.") % str(lastException)
			printl("", self, "C")
			return False

		if not PY2:
			response = response.decode("UTF-8")
		printl("response: " + response, self, "D")

		try:
			tree = etree.fromstring(response)
		except Exception:
			self.lastError = "no xml as response: " + str(response)

			printl("", self, "C")
			return False

		printl("", self, "C")
		return tree

	#===============================================================================
	#
	#===============================================================================
	def getXmlTreeFromUrl(self, url):
		printl("", self, "S")
		#Get the URL and server name. Get the XML and parse

		html = self.doRequest(url)

		try:
			tree = etree.fromstring(html)

			printl("", self, "C")
			return tree
		except Exception as e:
			printl("no parseable xml payload from " + str(url), self, "W")
			printl("parse error: " + str(e), self, "D")
			try:
				printl("payload was: " + repr(html)[:300], self, "D")
			except Exception:
				pass

			printl("", self, "C")
			return self.getFakeXml()

	#===============================================================================
	#
	#===============================================================================
	def getXmlTreeFromUrlPaged(self, url, pageSize=200):
		"""
		Fetch a container page by page using the X-Plex-Container-Start/Size
		headers and merge all children into one tree. Servers that ignore
		paging (no totalSize in the answer) are handled with one request.
		"""
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		mergedTree = None
		start = 0

		while True:
			pagingHeaders = {
				"X-Plex-Container-Start": str(start),
				"X-Plex-Container-Size": str(pageSize),
			}
			html = self.doRequest(url, extraHeaders=pagingHeaders)

			try:
				tree = etree.fromstring(html)
			except Exception as e:
				printl("no parseable xml payload at offset %d from %s" % (start, str(url)), self, "W")
				printl("parse error: " + str(e), self, "D")
				break

			if mergedTree is None:
				mergedTree = tree
			else:
				mergedTree.extend(list(tree))

			pageItemCount = len(tree)
			totalSize = tree.get("totalSize")

			if totalSize is None:
				# server ignored the paging headers and answered everything
				break

			start += pageSize

			if pageItemCount == 0 or start >= int(totalSize):
				break

		if mergedTree is None:
			printl("", self, "C")
			return self.getFakeXml()

		mergedTree.set("size", str(len(mergedTree)))

		printl("merged %d children" % len(mergedTree), self, "D")
		printl("", self, "C")
		return mergedTree

	#===============================================================================
	#
	#===============================================================================
	def getFakeXml(self):
		printl("", self, "S")

		xml = "<xml></xml>"
		tree = etree.fromstring(xml)

		printl("", self, "C")
		return tree

	#===============================================================================
	#
	#===============================================================================
	def sessionID(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.g_sessionID
	#===============================================================================
	#
	#===============================================================================

	def getLastErrorMessage(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.lastError

	#===============================================================================
	#
	#===============================================================================
	def getListFromTag(self, entry, tagName):
		#printl("", self, "S")
		tempList = []

		for child in entry:
			if child.tag == tagName:
				t = child.get('tag')
				t = t.encode("utf-8") if PY2 else t
				tempList.append(t)

		#printl("", self, "C")
		return tempList

	#=============================================================================
	#
	#=============================================================================
	def getImage(self, data, server, myType, transcode=True):
		"""
		Simply take a URL or path and determine how to format for images
		@ input: elementTree element, server name
		@ return formatted URL
		"""
		printl("", self, "S")
		printl("myType: " + str(myType), self, "D")

		image = data.get(myType, '').split('?t')[0]

		if image == '':
			printl("", self, "C")
			return ""

		elif image[0:4] == "http":
			printl("", self, "C")
			return image

		elif image[0] == '/':
			if transcode:
				printl("", self, "C")
				return self.photoTranscode(server, 'http://localhost:32400' + image)
			else:
				printl("", self, "C")
				return "%s://%s%s" % (self.http, server, image)

		else:
			printl("", self, "C")
			return ""

	#===========================================================================
	#
	#===========================================================================
	def photoTranscode(self, server, url, width=999, height=999):
		printl("", self, "S")

		transcode_url = None

		if width is not None and height is not None:
			transcode_url = '%s://%s/photo/:/transcode?url=%s&width=%s&height=%s' % (self.http, server, quote_plus(url), width, height)
			printl("transcode_url: " + str(transcode_url), self, "D")
		else:
			printl("unspecified width and height", self, "D")

		printl("", self, "C")
		return transcode_url

	#============================================================================
	#
	#============================================================================
	def watched(self, url):
		printl("", self, "S")

		if url.find("unscrobble") > 0:
			printl("Marking as unwatched with: " + url, self, "I")
		else:
			printl("Marking as watched with: " + url, self, "I")

		self.doRequest(url)

		printl("", self, "C")
		return

	#===============================================================================
	#
	#===============================================================================
	def deleteMedia(self, url):
		printl("", self, "S")
		printl("deleting media at: " + url, self, "I")

		return_value = True
		if return_value:
			printl("Deleting....")
			self.doRequest(url, myType="DELETE")

		printl("", self, "C")
		return True

	#===============================================================================
	#
	#===============================================================================
	def buildContextMenu(self, url, ratingKey, server):
		printl("", self, "S")

		context = {}

		#Initiate Library refresh
		refreshURL = url.replace("/all", "/refresh")
		libraryRefreshURL = refreshURL.split('?')[0]  # + self.get_aTokenForServer(server)
		context['libraryRefreshURL'] = libraryRefreshURL

		#Mark media unwatched
		unwatchedURL = "%s://%s/:/unscrobble?key=%s&identifier=com.plexapp.plugins.library" % (self.http, server, ratingKey)
		context['unwatchURL'] = unwatchedURL

		#Mark media watched
		watchedURL = "%s://%s/:/scrobble?key=%s&identifier=com.plexapp.plugins.library" % (self.http, server, ratingKey)
		context['watchedURL'] = watchedURL

		#Delete media from Library
		deleteURL = "%s://%s/library/metadata/%s" % (self.http, server, ratingKey)
		context['deleteURL'] = deleteURL

		printl("", self, "C")
		return context

#===============================================================================
# HELPER FUNCTIONS
#===============================================================================

	#===========================================================================
	#
	#===========================================================================
	def getUrlPathFormURL(self, url):
		printl("", self, "S")

		if url[0:4] == "http" or url[0:4] == "plex":
			printl("", self, "C")
			return "/" + "/".join(url.split('/')[3:])
		else:
			printl("", self, "C")
			return "/" + "/".join(url.split('/')[1:])

		#===========================================================================
	#
	#===========================================================================
	def getServerFromURL(self, url):
		"""
		Simply split the URL up and get the server portion, sans port
		@ input: url, woth or without protocol
		@ return: the URL server
		"""
		printl("", self, "S")
		printl("url: " + str(url), self, "D")

		if url[0:4] == "http" or url[0:4] == "plex":
			printl("", self, "C")
			return url.split('/')[2]
		else:
			printl("", self, "C")
			return url.split('/')[0]

	#============================================================================
	#
	#============================================================================
	def getLinkURL(self, url, pathData, server):
		"""
		Investigate the passed URL and determine what is required to
		turn it into a usable URL
		@ input: url, XML data and PM server address
		@ return: Usable http URL
		"""
		printl("", self, "S")

		path = pathData.get('key', '')
		printl("Path is " + path, self, "I")

		if path == '':
			printl("Empty Path", self, "I")
			printl("", self, "C")
			return

		#If key starts with http, then return it
		if path[0:4] == "http":
			printl("Detected http link", self, "I")
			printl("", self, "C")
			return path

		#If key starts with a / then prefix with server address
		elif path[0] == '/':
			printl("Detected base path link", self, "I")
			printl("", self, "C")
			return '%s://%s%s' % (self.http, server, path)

		#If key starts with plex:// then it requires transcoding
		elif path[0:5] == "plex:":
			printl("Detected plex link", self, "I")
			components = path.split('&')
			for i in components:
				if 'prefix=' in i:
					del components[components.index(i)]
					break
			if pathData.get('identifier', None):
				components.append('identifier=' + pathData['identifier'])

			path = '&'.join(components)
			printl("", self, "C")
			return 'plex://' + server + '/' + '/'.join(path.split('/')[3:])

		#Any thing else is assumed to be a relative path and is built on existing url
		else:
			printl("Detected relative link", self, "I")
			printl("", self, "C")
			return "%s/%s" % (url, path)

#===============================================================================
# GETTER FUNCTIONS
#===============================================================================

	#===============================================================================
	#
	#===============================================================================
	def getTranscodeSettings(self, override=False):
		printl("", self, "S")

		if override is True:
			printl("Transcode override. Will play media with addon transcoding settings", self, "I")
			self.g_transcode = "true"

		if self.g_transcode == "true":

			printl("We are set to Transcode, overriding stream selection", self, "I")

			printl("Transcode quality is " + self.serverConfig_quality, self, "I")
			protocols = "protocols=http-video;"
			videoDecoders = "videoDecoders=mpeg2video{profile:high&resolution:1080&level:51},mpeg4{profile:high&resolution:1080&level:51},mpeg1video{profile:high&resolution:1080&level:51},mp4{profile:high&resolution:1080&level:51},h264{profile:high&resolution:1080&level:51}"
			#dts is not running for some reason
			audioDecoders = "audioDecoders=mp3,aac"

			self.g_capability = quote_plus(protocols + ";" + videoDecoders + ";" + audioDecoders)

			printl("Plex Client Capability = " + self.g_capability, self, "I")

			printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def get_hTokenForServer(self, server):
		printl("", self, "S")

		printl("", self, "C")
		try:
			return self.g_myplex_accessTokenDict[server]["hToken"]
		except:
			revokeCacheFiles()
			return None

	#===========================================================================
	#
	#===========================================================================
	def get_aTokenForServer(self, server):
		printl("", self, "S")

		printl("", self, "C")
		try:
			return self.g_myplex_accessTokenDict[server]["aToken"]
		except:
			revokeCacheFiles()
			return None

	#===========================================================================
	#
	#===========================================================================
	def get_rawTokenForServer(self, server):
		try:
			return self.g_myplex_accessTokenDict[server].get("rawToken")
		except Exception:
			return None

	#===========================================================================
	#
	#===========================================================================
	def appendTokenToUrl(self, url, server=None):
		"""
		Append X-Plex-Token to a playback URL (idempotent). Media players
		fetch these URLs without our auth headers, so the token has to be
		part of the URL itself.
		"""
		if not url:
			return url

		if "X-Plex-Token=" in url:
			return url

		if server is None:
			server = self.getServerFromURL(url)

		token = self.get_rawTokenForServer(server)
		if not token:
			return url

		separator = "&" if "?" in url else "?"
		return url + separator + "X-Plex-Token=" + str(token)

	#===========================================================================
	#
	#===========================================================================
	def appendSessionToUrl(self, url):
		"""Append X-Plex-Session-Identifier to a playback URL (idempotent).

		The media player fetches the URL on its own, without our headers,
		so this has to travel in the URL for the server to recognise the
		stream as part of the session the timeline reports talk about.
		"""
		if not url or not self.g_playSessionID:
			return url

		if "X-Plex-Session-Identifier=" in url:
			return url

		separator = "&" if "?" in url else "?"
		return url + separator + "X-Plex-Session-Identifier=" + str(self.g_playSessionID)

	#===========================================================================
	#
	#===========================================================================
	def get_uTokenForServer(self, server):
		printl("", self, "S")

		printl("", self, "C")
		try:
			return self.g_myplex_accessTokenDict[server]["uToken"]
		except:
			revokeCacheFiles()
			return None

	#===========================================================================
	#
	#===========================================================================
	def getServerName(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.serverConfig_Name

	#===========================================================================
	#
	#===========================================================================
	def setServerDetails(self):
		printl("", self, "S")

		url = self.getServerFromURL(self.g_currentServer)
		xml = self.doRequest(url)

		printl("xml: " + str(xml), self, "D")

		try:
			tree = etree.fromstring(xml)
			self.g_serverVersion = str(tree.get("version").split('-')[0])
			self.g_multiUser = str(tree.get("multiuser")) == "1"
		except Exception as e:
			# an unreachable server root must not crash playback
			printl("could not read server details: " + str(e), self, "W")
			self.g_multiUser = False
			if not self.g_serverVersion:
				self.g_serverVersion = "unknown"

		printl("self.g_serverVersion: " + str(self.g_serverVersion), self, "D")
		printl("self.g_multiUser: " + str(self.g_multiUser), self, "D")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getUniversalTranscoderSettings(self):
		printl("", self, "S")

		if self.getTranscodeVideoCodec() == "hevc":
			videoQuality, videoResolution, maxVideoBitrate = self.getHevcTranscoderSettings()
			printl("", self, "C")
			return videoQuality, videoResolution, maxVideoBitrate

		quality = int(self.g_serverConfig.uniQuality.value)

		if quality == 0:
			#420x240, 320kbps
			videoResolution = "420x240"
			maxVideoBitrate = "320"
			videoQuality = "30"
		elif quality == 1:
			#576x320, 720 kbps
			videoResolution = "576x320"
			maxVideoBitrate = "720"
			videoQuality = "40"
		elif quality == 2:
			#720x480, 1,5mbps
			videoResolution = "720x480"
			maxVideoBitrate = "1500"
			videoQuality = "60"
		elif quality == 3:
			#1024x768, 2mbps
			videoResolution = "1024x768"
			maxVideoBitrate = "2000"
			videoQuality = "60"
		elif quality == 4:
			#1280x720, 3mbps
			videoResolution = "1280x720"
			maxVideoBitrate = "3000"
			videoQuality = "75"
		elif quality == 5:
			#1280x720, 4mbps
			videoResolution = "1280x720"
			maxVideoBitrate = "4000"
			videoQuality = "100"
		elif quality == 6:
			#1920x1080, 8mbps
			videoResolution = "1920x1080"
			maxVideoBitrate = "8000"
			videoQuality = "60"
		elif quality == 7:
			#1920x1080, 10mbps
			videoResolution = "1920x1080"
			maxVideoBitrate = "10000"
			videoQuality = "75"
		elif quality == 8:
			#1920x1080, 12mbps
			videoResolution = "1920x1080"
			maxVideoBitrate = "12000"
			videoQuality = "90"
		elif quality == 9:
			#1920x1080, 20mbps
			videoResolution = "1920x1080"
			maxVideoBitrate = "20000"
			videoQuality = "100"
		else:
			#1920x1080, 20mbps
			videoResolution = "no settings"
			maxVideoBitrate = "no settings"
			videoQuality = "no settings"

		printl("", self, "C")
		return videoQuality, videoResolution, maxVideoBitrate

	#===========================================================================
	#
	#===========================================================================
	def getHevcTranscoderSettings(self):
		"""Quality ladder for hevc output: (resolution, kbps, videoQuality).

		Same bitrates as the h264 ladder, but each step asks for a bigger
		frame - hevc carries at 3 Mbps roughly what h264 needs 5 for, so the
		efficiency is spent on resolution rather than on bandwidth, and the
		last step goes past the 1080p ceiling of the h264 ladder.

		It stops at 1440p on purpose. Measured against a 1.43 server: asking
		2560x1440 of a 3840x2072 source really delivered 2558x1380, while
		asking 3840x2160 came back downscaled to 1920x1036 - the server will
		not encode 2160p, so offering it would only promise what it cannot
		deliver.
		"""
		ladder = [
			("568x320", "320", "30"),
			("720x480", "720", "40"),
			("1280x720", "1500", "60"),
			("1280x720", "2000", "60"),
			("1920x1080", "3000", "75"),
			("1920x1080", "4000", "80"),
			("2560x1440", "8000", "90"),
		]

		try:
			quality = int(self.g_serverConfig.uniQualityHevc.value)
		except (AttributeError, ValueError):
			# a server entry written by an older version has no hevc ladder
			quality = -1

		if quality < 0 or quality >= len(ladder):
			printl("no hevc quality setting, falling back to 1080p", self, "W")
			quality = 4

		videoResolution, maxVideoBitrate, videoQuality = ladder[quality]
		printl("hevc quality %s: %s @ %s kbps" % (quality, videoResolution, maxVideoBitrate), self, "I")

		return videoQuality, videoResolution, maxVideoBitrate

	#===========================================================================
	#
	#===========================================================================
	def getTranscodeVideoCodec(self):
		"""Output codec chosen for this server, h264 when unset."""
		codec = getattr(self.g_serverConfig, "transcodeVideoCodec", None)

		return codec.value if codec is not None else "h264"

	#===========================================================================
	#
	#===========================================================================
	def getTranscodeProfileExtra(self):
		"""Client-profile directive asking the PMS to encode to HEVC.

		Plex has no videoCodec URL parameter - the output codec is negotiated
		through the client profile, so this goes out as X-Plex-Client-Profile-
		Extra on the request that starts the session. `protocol=` is
		mandatory: without it the server drops the directive ("ClientProfile
		Extra: missing protocol parameter") and quietly encodes H.264.

		Returns None for H.264, i.e. leave the server's own profile alone.
		"""
		if self.getTranscodeVideoCodec() != "hevc":
			return None

		return "append-transcode-target-codec(type=videoProfile&context=streaming&protocol=hls&videoCodec=hevc)"

	#=============================================================================
	#
	#=============================================================================
	def transcode(self, myID, url):
		printl("", self, "S")
		server = self.getServerFromURL(url)

		#Check for plex.tv user, which we need to alter to a master server
		if 'plexapp.com' in url:
			server = self.g_currentServer

		printl("Using preferred transcoding server: " + server, self, "I")

		filename = '/'.join(url.split('/')[3:])

		# the transcode has to run under the same id the timeline reports
		# talk about, otherwise the server sees a stream under one identity
		# and progress under another, and shows neither in its dashboard.
		# Upstream used the client uuid here, which never changes, so every
		# playback of the whole session shared one transcode id
		session = self.g_playSessionID or self.g_sessionID

		transcode = []
		if self.g_serverConfig.universalTranscoder.value:
			videoQuality, videoResolution, maxVideoBitrate = self.getUniversalTranscoderSettings()
			printl("Setting up HTTP Stream with universal transcoder", self, "I")
			streamPath = "video/:/transcode/universal"
			streamFile = 'start.m3u8'
			transcode.append("path=%s%s" % (quote_plus('http://127.0.0.1:32400'), quote_plus(self.urlPath)))
			transcode.append("session=%s" % session)
			transcode.append("protocol=hls")
			transcode.append("offset=0")
			transcode.append("3g=0")
			transcode.append("directPlay=0")
			transcode.append("directStream=0")
			transcode.append("videoQuality=" + videoQuality)
			transcode.append("videoResolution=" + videoResolution)
			transcode.append("maxVideoBitrate=" + maxVideoBitrate)
			transcode.append("subtitleSize=100")
			transcode.append("audioBoost=100")
			transcode.append("waitForSegments=1")

			# without mediaIndex the PMS transcodes the FIRST version of the
			# item no matter which one was chosen in the dialog
			if self.g_selectedMediaIndex is not None:
				transcode.append("mediaIndex=%s" % self.g_selectedMediaIndex)
				transcode.append("partIndex=0")
		else:
			printl("Setting up HTTP Stream", self, "I")
			streamPath = "video/:/transcode/segmented"
			streamFile = 'start.m3u8'
			transcode.append("identifier=com.plexapp.plugins.library")
			transcode.append("ratingKey=%s" % myID)
			transcode.append("offset=0")
			transcode.append("quality=%d" % int(self.serverConfig_quality))
			transcode.append("session=%s" % session)
			transcode.append("secondsPerSegment=%d" % int(self.g_segments))
			transcode.append("url=%s%s" % (quote_plus('http://127.0.0.1:32400/'), quote_plus(filename)))
			transcode.append("key=%s%s" % (quote_plus('http://127.0.0.1:32400/library/metadata/'), myID))
			transcode.append("3g=0")
			transcode.append("httpCookies=")
			transcode.append("userAgent=")

		streamParams = "%s/%s?%s" % (streamPath, streamFile, "&".join(transcode))
		streamURL = "http://%s/%s" % (server, streamParams)
		printl("Encoded HTTP Stream URL: " + str(streamURL), self, "I")

		# prefetch the master playlist: the PMS spins up the transcode
		# session and answers with the media playlist location(s)
		req = Request(self.appendTokenToUrl(streamURL, server), headers=getPlexHeader(self.g_sessionID))
		req.add_header('X-Plex-Client-Capabilities', self.g_capability)

		# this request is what opens the transcode: carrying the session id
		# is what lets the server file it under the playback the timeline
		# reports are about, instead of an anonymous transcode
		if self.g_playSessionID:
			req.add_header("X-Plex-Session-Identifier", str(self.g_playSessionID))

		# ask for HEVC when the user enabled it: this request is the one that
		# spins the session up, so the profile has to travel with it
		profileExtra = self.getTranscodeProfileExtra()
		if profileExtra:
			printl("requesting HEVC output from the transcoder", self, "I")
			req.add_header("X-Plex-Client-Profile-Name", "generic")
			req.add_header("X-Plex-Client-Profile-Extra", profileExtra)

		rawToken = self.get_rawTokenForServer(server)
		if rawToken:
			req.add_header("X-Plex-Token", rawToken)

		urls = []
		try:
			resp = urlopen(req)
			try:
				payload = resp.read()
			finally:
				resp.close()

			# the response is bytes on Python 3: decode before iterating,
			# otherwise the '#' comparison and the string formatting below
			# silently corrupt the URL (b'...' fragments)
			for line in payload.decode("utf-8", "replace").splitlines():
				line = line.strip()
				if not line or line.startswith('#'):
					continue

				if line.startswith("http"):
					absoluteUrl = line
				else:
					absoluteUrl = "http://%s/%s/%s" % (server, streamPath, line)

				urls.append(absoluteUrl)
				printl("Got: " + absoluteUrl, self, "I")

		except Exception as e:
			printl("master playlist prefetch failed: " + str(e), self, "W")

		if urls:
			fullURL = urls.pop()
		else:
			# hand the master playlist itself to the player;
			# GStreamer's hlsdemux resolves it on its own
			fullURL = streamURL

		fullURL = self.appendTokenToUrl(fullURL, server)

		printl("Transcoded media location URL " + fullURL, self, "I")

		printl("", self, "C")
		return fullURL

#===============================================================================
# HELPER
#===============================================================================

	#===============================================================================
	#
	#===============================================================================
	def getFullListEntry(self, entryData, url, viewState=None, isDirectory=False):
		printl("", self, "S")

		# TODO check after some time if we can delete this
		# if not isDirectory and "ratingKey" in entryData:
		# 	# build specific context menu entries
		# 	contextMenu = self.buildContextMenu(url, entryData['ratingKey'], entryData['server'])
		# else:
		# 	# directories have no contextMenu
		# 	contextMenu = None

		if "ratingKey" in entryData:
			contextMenu = self.buildContextMenu(url, entryData['ratingKey'], entryData['server'])
		else:
			contextMenu = None

		# build url for content
		nextUrl = '%s://%s%s' % (self.http, entryData['server'], entryData['key'])

		title = entryData.get('title', 'no Title')
		title = title.encode('utf-8') if PY2 else title
		content = title, entryData, contextMenu, viewState, nextUrl

		printl("", self, "C")
		return content

	#===========================================================================
	#
	#===========================================================================
	def getViewStateForShowEntry(self, entryData):
		printl("", self, "S")

		# modern PMS omits the counters on some answers
		if "viewedLeafCount" not in entryData or "leafCount" not in entryData:
			printl("", self, "C")
			return "unseen"

		# lets add this for another filter
		if int(entryData["viewedLeafCount"]) == int(entryData["leafCount"]):
			viewState = "seen"

		elif int(entryData["viewedLeafCount"]) > 0:
			viewState = "started"

		else:
			viewState = "unseen"

		printl("", self, "C")
		return viewState

	#===============================================================================
	#
	#===============================================================================
	def getViewStatefromViewCount(self, entryData):
		printl("", self, "S")

		# because it could be that this tags are not existing we write them via get to set them to zero if they dont
		viewCount = int(entryData.get('viewCount', 0))
		viewOffset = int(entryData.get('viewOffset', 0))

		if viewCount > 0:
			viewState = "seen"

		elif viewCount >= 0 and viewOffset > 0:
			viewState = "started"

		else:
			viewState = "unseen"

		printl("", self, "C")
		return viewState

	#===============================================================================
	#
	#===============================================================================
	def getServerConfig(self):
		printl("", self, "S")

		printl("", self, "C")
		return self.g_serverConfig
