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
import os
import time

from six import PY2
try:
	import cPickle as pickle
except Exception:
	import pickle
from Screens.Screen import Screen

from .DP_ViewFactory import getViews
from .DP_View import DP_View

from .DPH_Singleton import Singleton
from .DPH_CacheGuard import isCacheFileTrusted, secureCacheFile

from .__common__ import printl2 as printl
from . import SettingsStorage


#===============================================================================
#
#===============================================================================

# How long a cached listing pickle is trusted before a "cache"-sourced load
# (see loadLibraryData()/getLibraryData()) falls back to a live fetch anyway -
# bounds staleness (watched-state, newly added/removed items) to a short
# window instead of "forever until something forces an update", while still
# making flipping back and forth between recently-browsed folders instant.
CACHE_MAX_AGE_SECONDS = 300


class DP_LibMain(Screen):

	#===========================================================================
	#
	#===========================================================================
	def __init__(self, session, libraryName):
		printl("", self, "S")
		printl("libraryName: " + str(libraryName), self, "D")

		Screen.__init__(self, session)
		self._libraryName = libraryName

		self._views = getViews(libraryName)

		settings: SettingsStorage = Singleton().getSettingsInstance()

		if self._libraryName == "movies":
			self.currentViewIndex = int(settings.defaultMovieView.getValue())

		elif self._libraryName == "shows":
			self.currentViewIndex = int(settings.defaultShowView.getValue())

		elif self._libraryName == "music":
			self.currentViewIndex = int(settings.defaultMusicView.getValue())

		else:
			self.currentViewIndex = 0

		self.onFirstExecBegin.append(self.showView)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def showView(self):
		printl("", self, "S")

		viewParams = self._views[self.currentViewIndex][2]
		if PY2:
			m = __import__(self._views[self.currentViewIndex][1], globals(), locals(), [])
			self.session.openWithCallback(self.onViewClosed, m.getViewClass(), self._libraryName, self.loadLibrary, viewParams)
		else:
			modulename = self._views[self.currentViewIndex][1]
			if modulename == 'DP_ViewMovies':
				from .DP_ViewMovies import DPS_ViewMovies
				self.session.openWithCallback(self.onViewClosed, DPS_ViewMovies, self._libraryName, self.loadLibrary, viewParams)
			elif modulename == 'DP_ViewShows':
				from .DP_ViewShows import DPS_ViewShows
				self.session.openWithCallback(self.onViewClosed, DPS_ViewShows, self._libraryName, self.loadLibrary, viewParams)
			elif modulename == 'DP_ViewMusic':
				from .DP_ViewMusic import DPS_ViewMusic
				self.session.openWithCallback(self.onViewClosed, DPS_ViewMusic, self._libraryName, self.loadLibrary, viewParams)
			elif modulename == 'DP_ViewMixed':
				from .DP_ViewMixed import DPS_ViewMixed
				self.session.openWithCallback(self.onViewClosed, DPS_ViewMixed, self._libraryName, self.loadLibrary, viewParams)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def loadLibrary(self):
		printl("", self, "S")

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onViewClosed(self, cause=None):
		"""
		Called if View has closed, react on cause for example change to different view
		"""
		printl("", self, "S")
		printl("cause: %s" % str(cause), self, "D")

		if cause is not None:
			if cause[0] == DP_View.ON_CLOSED_CAUSE_SAVE_DEFAULT:
				self.close()

			elif cause[0] == DP_View.ON_CLOSED_CAUSE_CHANGE_VIEW or cause[0] == DP_View.ON_CLOSED_CAUSE_CHANGE_VIEW_FORCE_UPDATE:
				self.currentViewIndex += 1
				if len(self._views) <= self.currentViewIndex:
					self.currentViewIndex = 0

				if len(cause) >= 5 and cause[4] is not None:
					for i in range(len(self._views)):
						if cause[4] == self._views[i][1]:
							self.currentViewIndex = i
							break

				self.showView()

			else:
				printl("", self, "C")
				self.close()

		else:
			printl("", self, "C")
			self.close()

	#===========================================================================
	#
	#===========================================================================
	def loadLibraryData(self, entryData, forceUpdate):
		printl("", self, "S")

		url = entryData["contentUrl"]

		if "source" in entryData:
			try:
				uuid = entryData["uuid"]
			except Exception:
				uuid = None
		else:
			uuid = None

		if "nextViewMode" in entryData:
			nextViewMode = entryData["nextViewMode"]
			currentViewMode = entryData["currentViewMode"]
		else:
			nextViewMode = entryData["type"]
			currentViewMode = None

		# "cache" (read the on-disk pickle, see getLibraryData()) vs "plex"
		# (always fetch live - kept as the historical literal; it has
		# nothing to do with which backend is active, that dispatch happens
		# separately through Singleton().getMediaLibrary() inside
		# getLibraryDataFromPlex()). Without a uuid there is no cache slot
		# to read from; a specific single item's detail (key != "all") and
		# an explicit forceUpdate both always need fresh data.
		#
		# This used to force "plex" unconditionally the moment nextViewMode
		# was present - true for virtually every real listing - so the
		# cache written a few lines below in getLibraryData() was written
		# but never actually read back, on any screen, either backend
		# (matches the "always a small wait on every context change" you
		# noticed live - not something specific to Jellyfin).
		source = "cache" if uuid else "plex"

		if str(entryData.get('key')) != "all":
			source = "plex"

		if forceUpdate:
			source = "plex"

		library, mediaContainer = self.getLibraryData(source, url, nextViewMode, currentViewMode, uuid, forceUpdate)

		printl("", self, "C")
		return library, mediaContainer

	#===========================================================================
	#
	#===========================================================================
	def getLibraryData(self, source, url, nextViewMode, currentViewMode, uuid, forceUpdate=False):
		printl("", self, "S")

		settings: SettingsStorage = Singleton().getSettingsInstance()

		if settings.useCache.getValue():
			pickleFileExists = False
			regeneratePickleFile = False
			#noinspection PyAttributeOutsideInit
			self.pickleName = "%s%s_%s.cache" % (settings.cacheFolderPath.getValue(), uuid, nextViewMode)
			if os.path.exists(self.pickleName):
				pickleFileExists = True

			# Bounded staleness (CACHE_MAX_AGE_SECONDS) instead of trusting
			# the pickle indefinitely - this is the first time "source ==
			# cache" is actually reachable (see loadLibraryData()), so
			# nothing has ever exercised how stale a long-lived cache file
			# can get in practice.
			cacheIsFresh = pickleFileExists and (time.time() - os.path.getmtime(self.pickleName)) < CACHE_MAX_AGE_SECONDS

			if source == "cache" and cacheIsFresh:
				try:
					library = self.getLibraryDataFromPickle()
					printl("from pickle", self, "D")
				except Exception:
					printl("cache file not found", self, "D")
					library = self.getLibraryDataFromPlex(url, nextViewMode, currentViewMode)
					regeneratePickleFile = True
			else:
				library = self.getLibraryDataFromPlex(url, nextViewMode, currentViewMode)

				if forceUpdate or not cacheIsFresh:
					regeneratePickleFile = True

			if not pickleFileExists or regeneratePickleFile:
				printl("pickleFileExists: " + str(pickleFileExists), self, "D")
				printl("regeneratePickleFile: " + str(regeneratePickleFile), self, "D")
				self.generateCacheForSection(library)
		else:
			library = self.getLibraryDataFromPlex(url, nextViewMode, currentViewMode)

		printl("", self, "C")
		return library

	#===========================================================================
	#
	#===========================================================================
	def getLibraryDataFromPickle(self):
		printl("", self, "S")

		# pickle.load() executes the content of the file: loading one we did
		# not write ourselves amounts to running arbitrary code as root.
		if not isCacheFileTrusted(self.pickleName):
			printl("", self, "C")
			raise IOError("untrusted cache file: %s" % self.pickleName)

		fd = open(self.pickleName, "rb")
		pickleData = pickle.load(fd)
		fd.close()

		printl("", self, "C")
		return pickleData

	#===========================================================================
	#
	#===========================================================================
	def getLibraryDataFromPlex(self, url, nextViewMode, currentViewMode):
		printl("", self, "S")

		printl("nextViewMode: " + str(nextViewMode), self, "D")
		printl("currentViewMode: " + str(currentViewMode), self, "D")
		library = None
		mediaContainer = None

		# MUSIC
		if nextViewMode == "artist":
			library, mediaContainer = Singleton().getMediaLibrary().getMusicByArtist(url)

		elif nextViewMode == "ShowAlbums" or (currentViewMode == "ShowAlbums" and nextViewMode == "ShowDirectory"):
			library, mediaContainer = Singleton().getMediaLibrary().getMusicByAlbum(url)

		elif nextViewMode == "ShowTracks":
			library, mediaContainer = Singleton().getMediaLibrary().getMusicTracks(url)

		# MOVIES
		elif nextViewMode == "movie" or (currentViewMode == "ShowMovies" and nextViewMode == "ShowDirectory"):
			library, mediaContainer = Singleton().getMediaLibrary().getMoviesFromSection(url)

		elif nextViewMode == "mixed":
			library, mediaContainer = Singleton().getMediaLibrary().getMixedContentFromSection(url)

		# Plex-only: the top-level Playlists listing itself (<Playlist> XML
		# rows) - entering one specific playlist uses "mixed" above instead,
		# via its own "key" attribute. Jellyfin's Playlists row goes through
		# "mixed" directly even at this top level (see
		# JellyfinLibrary._collectionsAndPlaylistsEntries()), so this
		# branch is never reached for it.
		elif nextViewMode == "playlists":
			library, mediaContainer = Singleton().getMediaLibrary().getPlaylists(url)

		# Plex-only: Collections for one specific movie library section -
		# entering one specific collection uses "mixed" above instead, via
		# its own "key" attribute, same as a playlist.
		elif nextViewMode == "collections":
			library, mediaContainer = Singleton().getMediaLibrary().getCollectionsForSection(url)

		# SHOWS
		elif nextViewMode == "show" or (currentViewMode == "ShowShows" and nextViewMode == "ShowDirectory"):
			library, mediaContainer = Singleton().getMediaLibrary().getShowsFromSection(url)

		elif nextViewMode == "ShowEpisodesDirect":
			library, mediaContainer = Singleton().getMediaLibrary().getEpisodesOfSeason(url, directMode=True)

		elif nextViewMode == "ShowSeasons":
			library, mediaContainer = Singleton().getMediaLibrary().getSeasonsOfShow(url)

		elif nextViewMode == "ShowEpisodes":
			library, mediaContainer = Singleton().getMediaLibrary().getEpisodesOfSeason(url)

		printl("", self, "C")
		return library, mediaContainer

	#===========================================================================
	#
	#===========================================================================
	def generateCacheForSection(self, library):
		printl("", self, "S")

		try:
			pickleData = library
			fd = open(self.pickleName, "wb")
			pickle.dump(pickleData, fd, 2)  # pickle.HIGHEST_PROTOCOL
			fd.close()
			secureCacheFile(self.pickleName)
		except Exception as e:
			printl("Error while saving cache file: " + str(e), self, "D")

		printl("", self, "C")
