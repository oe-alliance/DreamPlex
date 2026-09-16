# -*- coding: utf-8 -*-
"""
DreamPlex Plugin by DonDavici, 2012
and jbleyel 2021
Jellyfin support by [Your Name], 2023

Original -> https://github.com/oe-alliance/DreamPlex
Fork -> https://github.com/oe-alliance/DreamPlex

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
from .JellyfinSettings import JellyfinSettings, buildAuthorizationHeaderValue
from ..DP_MediaLibrary import DP_MediaLibrary, RATING_KIND_FAVORITE

try:
	import cPickle as pickle
except Exception:
	import pickle

from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import quote_plus, unquote
from urllib.request import urlopen, Request
import urllib.error
import json
import uuid

from random import seed

from Screens.Screen import Screen

from ..__common__ import printl2 as printl, getUUID, getVersion
from .. import _
from .. import DPH_Vault
from ..DP_SettingsStorage import AuthorizationResult
from ..__plugin__ import getPlugin, Plugin

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
DEFAULT_PORT = "8096"

#===============================================================================
# JellyfinLibrary
#===============================================================================


class JellyfinLibrary(DP_MediaLibrary):

	g_sessionID = None
	g_sections = []
	serverConfig_Name = "JellyfinServer"
	g_host = "192.168.0.1"
	serverConfig_port = "8096"
	g_currentServer = None
	serverConfig_connectionType = None
	serverConfig_localAuth = None
	g_serverConfig = None
	g_accessToken = None
	g_userId = None
	g_deviceId = None
	g_serverUrl = None
	g_transcode = True
	g_playbackType = None
	g_sessionID = None
	g_showForeign = True
	g_streamControl = True
	g_channelId = None
	g_currentError = ""
	g_serverDict = {}
	g_serversList = []
	g_sectionCache = {}
	g_sectionCacheLoaded = False
	g_connectionType = None
	g_localAuth = None
	g_error = False
	g_showUnSeenCounts = False
	g_useFilterSections = False
	g_streamMode = False
	g_useBetaFeatures = False
	g_playtheme = False
	g_forcedvdplayer = False
	# A Recursive=true listing of a large library can take a few seconds to
	# come back even with light Fields (see getMediaData) - 5s was tight
	# enough that it timed out outright on a real library, indistinguishable
	# from "no data" until getLastErrorMessage() started surfacing it.
	g_connectionTimeout = 30
	g_serverVersion = None
	g_quality = None
	g_segments = None
	g_directMode = False
	g_directLocal = False
	g_universalTranscoder = False
	g_audioType = None
	g_subtitleType = None
	g_remotePathIdentifier = None
	g_remotePathIdentifiersList = None
	g_loadExtraData = False
	g_streamControl = True
	g_srtRenamingForDirectLocal = False
	g_subtitlesLanguage = "de"
	g_useForcedSubtitles = True
	g_lastResponse = None
	g_lastUrl = None
	g_lastAuthToken = None
	g_lastError = None
	# Set by _pick_stream_indices() (see getMediaOptionsToPlay()), same idea
	# and shape as DP_PlexLibrary's own attribute of this name - read back by
	# DP_Player.play() to auto-select this embedded subtitle once the native
	# player reports its track list (see DP_Player.subtitleChecker()).
	g_SelectedEmbeddedSubtitleData = None
	# Set by DP_ServerMenu right after a successful switch to a saved
	# profile (or a fresh login) - held in memory only, for the lifetime of
	# this JellyfinLibrary instance, never written to disk here. Used by
	# _tryRefreshToken() to re-authenticate transparently if the server
	# rejects the current token as expired. _sessionPin is None for a
	# PIN-less profile (nothing to re-derive, the password is already
	# plaintext) and set to the PIN for one that is encrypted, so a wrong
	# in-memory state can never leak a password for the wrong profile.
	_sessionPin = None
	_sessionPassword = None

	def __init__(self, session, serverConfig:JellyfinSettings=None, resolvedMyPlexAddress=None, machineIdentifier=None):
		printl("", self, "S")
		Screen.__init__(self, session)
		DP_MediaLibrary.__init__(self, session)

		self.g_serverConfig = serverConfig
		
		if serverConfig is not None:
			self.setServerDetails()
			
		printl("", self, "C")

	# -------------------------------------------------
	# Helpers
	# -------------------------------------------------
	def _user_id(self):
		try:
			return self.g_serverConfig._userId.getValue()
		except Exception:
			return self.g_userId

	def _token(self):
		try:
			return self.g_serverConfig._accessToken.getValue()
		except Exception:
			return self.g_accessToken

	def _build_url(self, path: str, params: dict | None = None, add_token: bool = False) -> str:
		base = path
		if not path.startswith("http"):
			if not path.startswith("/"):
				path = "/" + path
			base = (self.g_serverUrl or "") + path
		if params and len(params):
			from urllib.parse import urlencode
			sep = "&" if ("?" in base) else "?"
			base = base + sep + urlencode(params)
		if add_token:
			token = self._token()
			if token:
				# ?api_key=... was removed in Jellyfin 12.0 along with the
				# other legacy auth methods. These URLs end up in two very
				# different places: handed to doRequest() (our own fetch,
				# which already attaches a real Authorization header via
				# self.g_headers - this fragment is inert there, urllib
				# never sends a URL fragment over the wire) or, for direct
				# playback, embedded straight into an eServiceReference and
				# fetched by gstreamer/servicemp3 outside any of our code -
				# that path has no other way to receive a custom header.
				# Enigma2's own convention for that (used by other IPTV
				# plugins) is "url#Header=value&Header2=value2", parsed out
				# before the URL is handed to gstreamer - so this is the one
				# place that condition actually matters.
				headerValue = quote_plus(buildAuthorizationHeaderValue(token))
				base = base + f"#Authorization={headerValue}"
		return base

	def _request_json(self, method: str, path: str, params: dict | None = None, data: bytes | None = None, _retried: bool = False):
		url = self._build_url(path, params=params)
		self.g_lastUrl = url
		headers = getattr(self, 'g_headers', None) or {}
		req = Request(url, data=data, headers=headers)
		req.get_method = lambda: method.upper()
		try:
			resp = urlopen(req, timeout=self.g_connectionTimeout)
			body = resp.read()
			self.g_lastResponse = body
			# a successful request clears any error left over from a
			# previous one - otherwise a genuinely empty (but successfully
			# fetched) section would show a stale, unrelated error message
			# on top of "no data", from whatever last failed in this session
			self.g_currentError = ""
			try:
				return json.loads(body.decode('utf-8')) if body else None
			except Exception:
				return None
		except urllib.error.HTTPError as e:
			# Jellyfin tokens (unlike Plex's) can expire mid-session - retry
			# once, transparently, with a freshly re-authenticated token,
			# instead of surfacing a 401 the user would otherwise have to
			# work around by re-entering the server token by hand.
			if e.code == 401 and not _retried and self._tryRefreshToken():
				return self._request_json(method, path, params=params, data=data, _retried=True)
			self.g_lastError = str(e)
			self.g_currentError = str(e)
			return None
		except Exception as e:
			self.g_lastError = str(e)
			self.g_currentError = str(e)
			return None

	def _tryRefreshToken(self) -> bool:
		"""Re-authenticates with whatever credentials are available and
		updates the token this instance and the saved profile use. Returns
		False (without prompting the user - this runs from inside a plain
		data fetch) if there is no password to retry with, leaving the
		original 401 to surface as-is.

		_sessionPassword (set by DP_ServerMenu at switch time) only exists
		for the lifetime of this JellyfinLibrary instance - reopening the
		server menu without explicitly going through "switch user" (the
		normal case: DP_ServerMenu is recreated fresh every time, it does
		not replay the last switch) starts a new instance with it unset, so
		a token that expired since the previous session had nothing to
		refresh with here and every list came back silently empty. Two
		fallbacks close that gap, in order of how much we trust them: the
		active profile's own saved password (plaintext only - if it is PIN-
		encrypted we do not have the PIN either, so it is unusable here
		regardless), then the server-level password field, which
		authenticateUser() updates on every successful login and so holds
		whichever credentials were used last, from any profile."""
		printl("access token rejected, attempting silent re-authentication", self, "I")
		username = None
		try:
			username = self.g_serverConfig._username.getValue()
		except Exception:
			pass

		password = self._sessionPassword
		if not password:
			try:
				currentUserId = self.g_serverConfig._userId.getValue()
				for u in self.g_serverConfig.listUsers():
					if u.id.getValue() == currentUserId:
						storedPassword = u.password.getValue()
						if storedPassword and not DPH_Vault.isEncrypted(storedPassword):
							password = storedPassword
						break
			except Exception:
				pass
		if not password:
			try:
				password = self.g_serverConfig._password.getValue()
			except Exception:
				pass

		if not username or not password:
			printl("no password available anywhere, cannot refresh silently", self, "W")
			return False

		try:
			ok, info = self.g_serverConfig.authenticateUser(None, username, password)
		except Exception as e:
			printl("silent re-authentication failed: " + str(e), self, "W")
			return False
		if not ok:
			return False

		newToken = info.get(AuthorizationResult.CREDENTIALS)
		userId = info.get(AuthorizationResult.ID)
		if not newToken:
			return False

		self.setAccessTokenHeader(self.g_currentServer, newToken)
		try:
			# _token()/_build_url(add_token=True) read the server-level
			# field, not g_accessToken - keep it in sync or a stream/image
			# URL built right after a refresh would still embed the stale
			# token as ?api_key=...
			self.g_serverConfig._accessToken.setValue(newToken)
		except Exception:
			pass

		# persist the refreshed token on the saved profile too, re-encrypted
		# if this profile is PIN-protected, so a plain restart does not need
		# another silent refresh right away
		try:
			for u in self.g_serverConfig.listUsers():
				if u.id.getValue() == (userId or self._user_id()):
					if self._sessionPin:
						u.token.setValue(DPH_Vault.encrypt(newToken, self._sessionPin))
						u.password.setValue(DPH_Vault.encrypt(password, self._sessionPin))
					else:
						u.token.setValue(newToken)
						u.password.setValue(password)
					self.g_serverConfig.saveChanges()
					break
		except Exception as e:
			printl("could not persist refreshed token: " + str(e), self, "W")

		printl("silent re-authentication succeeded", self, "I")
		return True

	def _preferred_language(self) -> str:
		try:
			lang = self.g_serverConfig._subtitlesLanguage.getValue()
			return (lang or "").lower()
		except Exception:
			return ""

	def _preferred_audio_language(self) -> str:
		try:
			lang = self.g_serverConfig._audioLanguage.getValue()
			return (lang or "").lower()
		except Exception:
			return ""

	def _use_forced_subtitles(self) -> bool:
		try:
			return bool(self.g_serverConfig._useForcedSubtitles.getValue())
		except Exception:
			return False

	def _map_quality_to_bitrate(self) -> int:
		# Mappa il setting qualità ad un bitrate massimo ragionevole
		mapping = {
			"0": 64_000,
			"1": 96_000,
			"2": 208_000,
			"3": 320_000,
			"4": 720_000,
			"5": 1_500_000,
			"6": 2_000_000,
			"7": 4_000_000,
			"8": 8_000_000,
			"9": 10_000_000,
			"10": 12_000_000,
			"11": 20_000_000,
			"12": 50_000_000,  # Original/very high
		}
		try:
			q = self.g_serverConfig._quality.getValue()
			return mapping.get(str(q), 8_000_000)
		except Exception:
			return 8_000_000

	def _pick_stream_indices(self, myId) -> tuple[int | None, int | None]:
		# Ritorna (audioIndex, subtitleIndex) in base a lingua preferita e forced
		info = self._request_json("GET", f"/Users/{self._user_id()}/Items/{myId}", params={"Fields": "MediaStreams"}) or {}
		streams = info.get('MediaStreams', []) or []
		pref_lang = self._preferred_language()
		pref_audio = self._preferred_audio_language() or pref_lang
		prefer_forced = self._use_forced_subtitles()

		audio_candidates = [s for s in streams if s.get('Type') == 'Audio']
		sub_candidates = [s for s in streams if s.get('Type') == 'Subtitle']

		audio_idx = None
		# Se disponibile lingua preferita, sceglila, altrimenti primo audio
		for s in audio_candidates:
			if (s.get('Language') or '').lower() == pref_audio and s.get('Index') is not None:
				audio_idx = s.get('Index')
				break
		if audio_idx is None and audio_candidates:
			audio_idx = audio_candidates[0].get('Index')

		sub_idx = None
		forced_stream = None
		# Preferisci forced se richiesto
		if prefer_forced:
			forced = [s for s in sub_candidates if s.get('IsForced')]
			if forced:
				sub_idx = forced[0].get('Index')
				forced_stream = forced[0]
		if sub_idx is None and pref_lang:
			for s in sub_candidates:
				if (s.get('Language') or '').lower() == pref_lang and s.get('Index') is not None:
					sub_idx = s.get('Index')
					break

		# Mirrors DP_PlexLibrary.getStreamDataById(): only auto-select an
		# embedded subtitle for DP_Player's native-track watcher (see
		# getSelectedEmbeddedSubtitleData()/DP_Player.play()) when it is
		# specifically the *forced* stream and the user has that setting on
		# - a plain language-only match is left to the SubtitleStreamIndex/
		# SubtitleMethod request params above instead, same split Plex uses.
		if forced_stream is not None:
			self.g_SelectedEmbeddedSubtitleData = {
				'id': forced_stream.get('Index'),
				'index': forced_stream.get('Index'),
				'language': forced_stream.get('Language') or '',
				'languageCode': forced_stream.get('Language') or '',
				'format': forced_stream.get('Codec') or '',
				'partid': myId,
			}
		else:
			self.g_SelectedEmbeddedSubtitleData = None

		return audio_idx, sub_idx

	def _stream_params(self, myId, direct=True, aidx_override: int | None = None, sidx_override: int | None = None) -> dict:
		params = {}
		if direct:
			params['static'] = 'true'
		else:
			# Parametri base per HLS
			params.update(self.getTranscodeSettings())
		aidx, sidx = self._pick_stream_indices(myId)
		if aidx_override is not None:
			aidx = aidx_override
		if sidx_override is not None:
			sidx = sidx_override
		if aidx is not None:
			params['AudioStreamIndex'] = aidx
		if sidx is not None:
			params['SubtitleStreamIndex'] = sidx
			# consegna sottotitoli esterni/embedded in base al setting
			try:
				meth = self.g_serverConfig._subtitleMethod.getValue() or 'External'
			except Exception:
				meth = 'External'
			params['SubtitleMethod'] = meth
		# Bitrate massimo per entrambe le modalità (diretto potrebbe ignorarlo)
		# Permetti override tramite customMaxBitrate
		try:
			custom = int(self.g_serverConfig._customMaxBitrate.getValue() or 0)
		except Exception:
			custom = 0
		params['MaxStreamingBitrate'] = custom if custom > 0 else self._map_quality_to_bitrate()
		return params

	def setPlaybackType(self, myType):
		printl("", self, "S")
		self.g_playbackType = myType
		printl("", self, "C")

	def getSectionTypes(self):
		printl("", self, "S")

		# DP_ServerMenu.okbuttonClick() reads selection[1]/[2]/[3] off each
		# row as (title, menu constant, entry-type key, entryData dict) -
		# mirroring DP_PlexLibrary.getSectionTypes(). Plain strings used to be
		# returned here instead: selection[1] indexed into the string itself
		# (e.g. "movies"[1] == "o"), so every row rendered as a single letter
		# and selecting one crashed on entryData.get(...) since entryData
		# ended up being a single character too.
		entryData = {}
		fullList = [
			(_("Movies"), Plugin.MENU_MOVIES, "movieEntry", entryData),
			(_("Tv Shows"), Plugin.MENU_TVSHOWS, "showEntry", entryData),
			(_("Music"), Plugin.MENU_MUSIC, "musicEntry", entryData),
		]
		fullList.extend(self._collectionsAndPlaylistsEntries())

		printl("", self, "C")
		return fullList

	#===========================================================================
	# Shared by getSectionTypes() (the default, "summarized" top-level menu -
	# settings.summerizeSections defaults to True, so this is what most users
	# actually see) and getAllSections() (the unfiltered listing shown when
	# that setting is off) - see the "Collections"/"Playlists" comment on the
	# latter for why these need their own rows instead of coming through
	# Views like Movies/TV Shows/Music do.
	#===========================================================================
	def _collectionsAndPlaylistsEntries(self):
		entries = []
		for title, itemType, uuidSuffix in ((_('Collections'), 'BoxSet', 'collections'), (_('Playlists'), 'Playlist', 'playlists')):
			entryData = {
				'contentUrl': {'includeTypes': itemType, 'recursive': True},
				'type': 'movie',
				'currentViewMode': 'movie',
				'nextViewMode': 'mixed',
				'source': 'jellyfin',
				'uuid': 'jellyfin-' + uuidSuffix,
			}
			entries.append((title, getPlugin('mixed', Plugin.MENU_MIXED), 'mixedEntry', entryData))
		return entries

	def getServerSectionPaths(self) -> list[str]:
		printl("", self, "S")
		
		paths = []
		
		printl("", self, "C")
		return paths

	# Maps a Jellyfin view's CollectionType to the skin's MenuEntryCompare
	# tag and the Plugin registered for it - mirrors DP_PlexLibrary.
	# getAllSections()'s non-filter branch (fullList.append((title,
	# getPlugin(pid, MENU_x), entryKey, entryData))).
	# The first tuple element is compared against getServerData()'s myFilter,
	# NOT used for getPlugin() lookups (getSectionFilter() below does its own,
	# separate "tvshows" pid for that) - DP_ServerMenu.py's MENU_TVSHOWS
	# branch calls getServerData("tvshow"), singular, matching
	# DP_PlexLibrary.getAllSections()'s own "tvshow" convention. Using the
	# plural here meant myFilter never matched, silently dropping every TV
	# library from the "Serie TV" summarized menu entry.
	_SECTION_TYPE_MAP = {
		'movies': ('movies', Plugin.MENU_MOVIES, 'movieEntry'),
		'tvshows': ('tvshow', Plugin.MENU_TVSHOWS, 'showEntry'),
		'music': ('music', Plugin.MENU_MUSIC, 'musicEntry'),
	}

	def getAllSections(self, myFilter=None, serverFilterActive=False):
		printl("", self, "S")
		fullList = []
		user_id = self._user_id()
		if not user_id:
			printl("No userId for Jellyfin", self, "E")
			return fullList
		data = self._request_json("GET", f"/Users/{user_id}/Views", params={"IncludeHidden": "false", "IncludeExternalContent": "false"})
		if data and isinstance(data, dict):
			for item in data.get('Items', []) or []:
				collectionType = item.get('CollectionType')
				mapping = self._SECTION_TYPE_MAP.get(collectionType)
				if mapping is None:
					# unmapped view type (playlists, boxsets, mixed content, ...) -
					# not handled by getSectionFilter() yet, skip rather than
					# render a row the rest of the UI cannot act on
					continue

				pid, where, entryKey = mapping
				if myFilter is not None and myFilter != pid:
					continue

				entryData = {
					'title': item.get('Name'),
					'id': item.get('Id'),
					'collectionType': collectionType,
					'type': item.get('Type'),
					'path': f"/Users/{user_id}/Items?ParentId={item.get('Id')}",
				}
				# selection[1] must stay the literal Plugin.MENU_FILTER int, so
				# DP_ServerMenu.okbuttonClick() takes the MENU_FILTER branch and
				# opens getSectionFilter()'s "All/Unwatched/..." submenu, exactly
				# like DP_PlexLibrary's g_useFilterSections branch - a bare dict
				# used to be returned here instead, crashing the skin's
				# MenuEntryCompare converter, which indexes the selected row as
				# row[2].
				fullList.append((_(entryData['title']), Plugin.MENU_FILTER, entryKey, entryData))

		# Collections (BoxSet) and Playlists are user-level items, not tied
		# to one library section the way Movies/TV Shows/Music are - Views
		# above never returns them, so they get their own rows here instead,
		# mirroring how DP_PlexLibrary.getAllSections() inserts "On Deck"/
		# "New". Only when showing the full unfiltered menu: a filtered
		# view (myFilter set) is asking for one specific section type, which
		# neither of these is.
		if myFilter is None and user_id:
			fullList.extend(self._collectionsAndPlaylistsEntries())

		printl("", self, "C")
		return fullList

	def getSectionFilter(self, incomingEntryData):
		printl("", self, "S")
		filters = []
		section_type = incomingEntryData.get('collectionType') or incomingEntryData.get('type') or ''
		section_id = incomingEntryData.get('id') or incomingEntryData.get('Id')

		# Helper per creare tuple menu compatibili con la UI.
		# DP_ServerMenu.okbuttonClick() reads a non-int selection[1] as
		# "executable" and calls DP_LibMain.loadLibraryData(entryData, ...),
		# which unconditionally does entryData["contentUrl"] and, unless
		# "nextViewMode" is present, falls back to entryData["type"] - neither
		# of which our filter params dict (parentId/sortBy/includeTypes/...)
		# had, so picking any filter here used to crash with KeyError:
		# 'contentUrl'. contentUrl is set to the entryData dict itself (self-
		# reference) rather than a frozen copy, so it stays in sync when
		# _onJellyfinPromptEntered() in DP_ServerMenu later adds genres/years/
		# searchTerm/rating/runtime to the very same dict.
		_NEXT_VIEW_MODE_BY_PID = {'movies': 'movie', 'tvshows': 'show', 'music': 'artist'}

		def _entry_tuple(title, pid, where, entryKey, dataDict, nextViewMode=None):
			entryData = dict(dataDict)
			entryData['nextViewMode'] = nextViewMode or _NEXT_VIEW_MODE_BY_PID.get(pid, 'movie')
			entryData['currentViewMode'] = ''
			entryData['contentUrl'] = entryData
			# "uuid" keys the disk cache (cacheFolderPath/<uuid>_<nextViewMode>.
			# cache| - without it every filter of every Jellyfin library shares
			# the single key "None_movie.cache" and would silently serve each
			# other's cached results. section_id (the Jellyfin view/library id)
			# is unique per library, so it is reused here as the uuid.
			entryData['uuid'] = section_id
			entryData['source'] = 'jellyfin'
			return (title, getPlugin(pid, where), entryKey, entryData)

		if section_type in ('movies', 'Movie'):
			base = {'parentId': section_id, 'includeTypes': 'Movie'}
			# Tutti (A-Z)
			filters.append(_entry_tuple(_('All (A-Z)'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='Name', sortOrder='Ascending')))
			# Z-A
			filters.append(_entry_tuple(_('All (Z-A)'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='Name', sortOrder='Descending')))
			# Non visti
			filters.append(_entry_tuple(_('Unwatched'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='Name', sortOrder='Ascending', unwatchedOnly=True)))
			# Aggiunti di recente
			filters.append(_entry_tuple(_('Recently Added'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='DateCreated', sortOrder='Descending')))
			# Più visti
			filters.append(_entry_tuple(_('Most Played'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='PlayCount', sortOrder='Descending')))
			# Casuale
			filters.append(_entry_tuple(_('Random'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										dict(base, sortBy='Random', sortOrder='Ascending')))
			# Per cartelle: elenco non ricorsivo del livello superiore della
			# libreria - _to_entry() marca le sottocartelle come tagType
			# "Directory" (nextViewMode "ShowDirectory"), così ogni ok
			# ridiscende di un livello con lo stesso meccanismo del drill-down
			# di Plex, invece di forzare IncludeItemTypes=Movie che le
			# nasconderebbe.
			filters.append(_entry_tuple(_('By Folder'), 'movies', Plugin.MENU_MOVIES, 'movieEntry',
										{'parentId': section_id, 'recursive': False, 'sortBy': 'IsFolder,Name', 'sortOrder': 'Descending,Ascending'}))

		elif section_type in ('tvshows', 'Series', 'show', 'episode'):
			base = {'parentId': section_id, 'includeTypes': 'Series'}
			filters.append(_entry_tuple(_('All (A-Z)'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='Name', sortOrder='Ascending')))
			filters.append(_entry_tuple(_('All (Z-A)'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='Name', sortOrder='Descending')))
			filters.append(_entry_tuple(_('Unwatched'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='Name', sortOrder='Ascending', unwatchedOnly=True)))
			filters.append(_entry_tuple(_('Recently Added'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='DateCreated', sortOrder='Descending')))
			filters.append(_entry_tuple(_('Most Played'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='PlayCount', sortOrder='Descending')))
			filters.append(_entry_tuple(_('Random'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										dict(base, sortBy='Random', sortOrder='Ascending')))
			filters.append(_entry_tuple(_('By Folder'), 'tvshows', Plugin.MENU_TVSHOWS, 'showEntry',
										{'parentId': section_id, 'recursive': False, 'sortBy': 'IsFolder,Name', 'sortOrder': 'Descending,Ascending'}))

		elif section_type in ('music', 'Audio', 'artist'):
			# Artisti / Album / Tracce
			base = {'parentId': section_id}
			filters.append(_entry_tuple(_('Artists'), 'music', Plugin.MENU_MUSIC, 'musicEntry',
										dict(base, includeTypes='MusicArtist', sortBy='Name', sortOrder='Ascending'),
										nextViewMode='artist'))
			filters.append(_entry_tuple(_('Albums'), 'music', Plugin.MENU_MUSIC, 'musicEntry',
										dict(base, includeTypes='MusicAlbum', sortBy='Name', sortOrder='Ascending'),
										nextViewMode='ShowAlbums'))
			filters.append(_entry_tuple(_('Tracks'), 'music', Plugin.MENU_MUSIC, 'musicEntry',
										dict(base, includeTypes='Audio', sortBy='Name', sortOrder='Ascending'),
										nextViewMode='ShowTracks'))

		# Advanced filter entries (user input)
		if section_type in ('movies', 'Movie', 'tvshows', 'Series'):
			# By Genre...
			base = {'parentId': section_id}
			include = 'Movie' if section_type in ('movies', 'Movie') else 'Series'
			filters.append(_entry_tuple(_('By Genre…'),
										'movies' if include == 'Movie' else 'tvshows',
										Plugin.MENU_MOVIES if include == 'Movie' else Plugin.MENU_TVSHOWS,
										'movieEntry' if include == 'Movie' else 'showEntry',
										dict(base, includeTypes=include, jellyfinPrompt='genre')))
			# By Year…
			filters.append(_entry_tuple(_('By Year…'),
										'movies' if include == 'Movie' else 'tvshows',
										Plugin.MENU_MOVIES if include == 'Movie' else Plugin.MENU_TVSHOWS,
										'movieEntry' if include == 'Movie' else 'showEntry',
										dict(base, includeTypes=include, jellyfinPrompt='year')))
			# Search…
			filters.append(_entry_tuple(_('Search…'),
										'movies' if include == 'Movie' else 'tvshows',
										Plugin.MENU_MOVIES if include == 'Movie' else Plugin.MENU_TVSHOWS,
										'movieEntry' if include == 'Movie' else 'showEntry',
										dict(base, includeTypes=include, jellyfinPrompt='search')))
			# By Rating…
			filters.append(_entry_tuple(_('By Rating…'),
										'movies' if include == 'Movie' else 'tvshows',
										Plugin.MENU_MOVIES if include == 'Movie' else Plugin.MENU_TVSHOWS,
										'movieEntry' if include == 'Movie' else 'showEntry',
										dict(base, includeTypes=include, jellyfinPrompt='rating')))
			# By Duration…
			filters.append(_entry_tuple(_('By Duration…'),
										'movies' if include == 'Movie' else 'tvshows',
										Plugin.MENU_MOVIES if include == 'Movie' else Plugin.MENU_TVSHOWS,
										'movieEntry' if include == 'Movie' else 'showEntry',
										dict(base, includeTypes=include, jellyfinPrompt='runtime')))

		printl("", self, "C")
		return filters

	# DP_LibMain.getLibraryDataFromPlex() always unpacks these as
	# (library, mediaContainer) - a bare list here crashed with
	# "ValueError: not enough/too many values to unpack" the moment any of
	# these was reached. There is no per-section metadata worth exposing yet,
	# so mediaContainer is a minimal stand-in: DP_ViewShows indexes
	# self.mediaContainer["title2"] directly (no .get()), so the key must be
	# present even though we have nothing meaningful to put in it.
	def _mediaContainer(self):
		return {"title1": "", "title2": ""}

	def getMoviesFromSection(self, url):
		printl("", self, "S")
		movies, _mc = self.getMediaData(url, "movies", "movie", "ShowMovies")
		printl("", self, "C")
		return movies, _mc

	def getMixedContentFromSection(self, url, fromRemotePlayer=False):
		printl("", self, "S")
		content, _mc = self.getMediaData(url, None, "mixed", "ShowMovies", fromRemotePlayer=fromRemotePlayer)
		printl("", self, "C")
		return content, _mc

	def getMusicByArtist(self, url):
		printl("", self, "S")
		music, _mc = self.getMediaData(url, "music", "artist", "ShowArtists")
		printl("", self, "C")
		return music, _mc

	def getMusicByAlbum(self, url):
		printl("", self, "S")
		music, _mc = self.getMediaData(url, "music", "ShowAlbums", "ShowArtists")
		printl("", self, "C")
		return music, _mc

	def getMusicTracks(self, url):
		printl("", self, "S")
		tracks, _mc = self.getMediaData(url, "music", "ShowTracks", "ShowAlbums")
		printl("", self, "C")
		return tracks, _mc

	def getShowsFromSection(self, url):
		printl("", self, "S")
		shows, _mc = self.getMediaData(url, "tvshows", "show", "ShowShows")
		printl("", self, "C")
		return shows, _mc

	def getSeasonsOfShow(self, url):
		printl("", self, "S")
		seasons = []
		user_id = self._user_id()
		if not user_id:
			return seasons, self._mediaContainer()
		series_id = url
		if not series_id or not series_id.isalnum():
			# if a full path is passed, try to parse last id segment
			series_id = str(url).split("/")[-1]
		data = self._request_json("GET", f"/Shows/{series_id}/Seasons", params={"UserId": user_id, "Fields": "ChildCount,RecursiveItemCount,Overview,PrimaryImageAspectRatio,People,Studios"})
		if data and isinstance(data, dict):
			for item in data.get('Items', []) or []:
				seasons.append(self._to_entry(item, currentViewMode="ShowSeasons"))
		printl("", self, "C")
		return seasons, self._mediaContainer()

	def getImageData(self, entryData, entry, server, switchMedias=False):
		printl("", self, "S")
		# entryData expected to contain an 'id' and possibly 'ImageTags'
		if not entryData:
			printl("", self, "C")
			return None
		item_id = entryData.get('Id') or entryData.get('id') or entry
		if not item_id:
			printl("", self, "C")
			return None
		# Build primary image URL (let the UI layer size/transcode if needed)
		img_url = self._build_url(f"/Items/{item_id}/Images/Primary", params={"maxWidth": 600, "maxHeight": 900}, add_token=True)
		printl("", self, "C")
		return img_url

	def getEpisodesOfSeason(self, url, directMode=False):
		printl("", self, "S")
		episodes = []
		user_id = self._user_id()
		if not user_id:
			return episodes, self._mediaContainer()
		season_id = url
		if not season_id or not season_id.isalnum():
			season_id = str(url).split("/")[-1]
		data = self._request_json("GET", f"/Users/{user_id}/Items", params={"ParentId": season_id, "IncludeItemTypes": "Episode", "Fields": "PrimaryImageAspectRatio,Path,Overview,MediaSources,MediaStreams,People,ChildCount,RecursiveItemCount"})
		if data and isinstance(data, dict):
			for item in data.get('Items', []) or []:
				episodes.append(self._to_entry(item, currentViewMode="ShowEpisodesDirect" if directMode else "ShowEpisodes"))
		printl("", self, "C")
		return episodes, self._mediaContainer()

	def getMediaData(self, url, tagType, nextViewMode, currentViewMode, switchMedias=False, fromRemotePlayer=False):
		printl("", self, "S")
		# Generic dispatcher over Items endpoint
		media = []
		user_id = self._user_id()
		if not user_id:
			return media, self._mediaContainer()
		include_types = None
		if tagType == "movies":
			include_types = "Movie"
		elif tagType == "tvshows":
			include_types = "Series"
		elif tagType == "seasons":
			include_types = "Season"
		elif tagType == "episodes":
			include_types = "Episode"
		elif tagType == "music":
			include_types = "Audio"
		# MediaSources/MediaStreams/People/Studios were requested for every
		# row here too, on top of a Recursive=true query that already dumps
		# the whole section in one shot - on a real library that combination
		# took over the connection timeout (5s) and the request came back as
		# a plain timeout, indistinguishable from "genuinely no data" until
		# getLastErrorMessage() surfaced it. Those fields are only used to
		# populate the detail panel (mediaDataArr, cast/director/studio) of
		# whichever single item is currently selected - not needed to render
		# the list itself, so they are dropped here. The detail panel will
		# show "unknown"/blank for those until a per-item fetch is added.
		params = {"Recursive": "true", "Fields": "PrimaryImageAspectRatio,Path,Overview,ChildCount,RecursiveItemCount"}
		# Threaded into every row below as refreshParentId - same id the
		# "refresh Library" button (DP_View.initiateRefresh()) later POSTs
		# to /Items/{id}/Refresh, see refreshLibrarySection(). Every row on
		# one listing shares the same id, same as Plex's own
		# context['libraryRefreshURL'] (built once per page, not per row).
		parent_id = None
		# Se url è un dict con filtri/ordinamenti, applicali
		if isinstance(url, dict):
			parent_id = url.get('parentId') or url.get('ParentId')
			if parent_id:
				params['ParentId'] = parent_id
			if url.get('unwatchedOnly'):
				params['IsPlayed'] = 'false'
			if url.get('genres'):
				# Jellyfin usa "Genres" come filtro testuale, separati da virgola
				params['Genres'] = ','.join(url.get('genres')) if isinstance(url.get('genres'), (list, tuple)) else url.get('genres')
			if url.get('years'):
				params['Years'] = ','.join(str(y) for y in url.get('years')) if isinstance(url.get('years'), (list, tuple)) else str(url.get('years'))
			if url.get('searchTerm'):
				params['SearchTerm'] = url.get('searchTerm')
			# Filtri aggiuntivi
			# Rating: singolo o range
			if url.get('rating') is not None:
				try:
					params['MinCommunityRating'] = float(url.get('rating'))
				except Exception:
					pass
			if url.get('ratingMin') is not None:
				try:
					params['MinCommunityRating'] = float(url.get('ratingMin'))
				except Exception:
					pass
			if url.get('ratingMax') is not None:
				try:
					params['MaxCommunityRating'] = float(url.get('ratingMax'))
				except Exception:
					pass
			# Runtime in ticks (100ns), supporta minimo/massimo
			if url.get('runtimeMinTicks') is not None:
				params['MinRuntimeTicks'] = int(url.get('runtimeMinTicks'))
			if url.get('runtimeMaxTicks') is not None:
				params['MaxRuntimeTicks'] = int(url.get('runtimeMaxTicks'))
			if url.get('sortBy'):
				params['SortBy'] = url.get('sortBy')
			if url.get('sortOrder'):
				params['SortOrder'] = url.get('sortOrder')
			# "By Folder" browsing: a non-recursive listing of the current
			# folder, so it must NOT restrict IncludeItemTypes to
			# Movie/Series - that would filter out the very sub-folders being
			# browsed, leaving only files and no way to descend.
			if 'recursive' in url:
				params['Recursive'] = 'true' if url.get('recursive') else 'false'
				if not url.get('recursive') and not url.get('includeTypes'):
					include_types = None
			if url.get('includeTypes'):
				include_types = url.get('includeTypes')
		if include_types:
			params["IncludeItemTypes"] = include_types
		if isinstance(url, str) and url and url.isalnum():
			params["ParentId"] = url
			parent_id = url
			# A bare id here only ever comes from descending into a "By
			# Folder" sub-folder (its own id, set as nextUrl by _to_entry()) -
			# keep it non-recursive so each ok press goes one level deeper
			# instead of suddenly dumping the whole subtree flattened.
			params["Recursive"] = "false"
			params.pop("IncludeItemTypes", None)
		# The heavy per-item fields (codec/audio streams, cast, studios) were
		# dropped from the default Fields above because a Recursive=true dump
		# of a whole library times out with them. A single folder's contents
		# is a different story - that is a handful of items, and the whole
		# point of opening a folder is to see what is actually in it, so ask
		# for the full set whenever this fetch is not the big flat dump.
		if params.get("Recursive") != "true":
			params["Fields"] += ",MediaSources,MediaStreams,People,Studios"
		if isinstance(url, str) and url and url.isalnum():
			data = self._request_json("GET", f"/Users/{user_id}/Items", params=params)
		elif isinstance(url, str):
			data = self._request_json("GET", url)
		else:
			data = self._request_json("GET", f"/Users/{user_id}/Items", params=params)
		if data and isinstance(data, dict):
			for item in data.get('Items', []) or []:
				media.append(self._to_entry(item, currentViewMode=currentViewMode, refreshParentId=parent_id))
		printl("", self, "C")
		return media, self._mediaContainer()

	def getDirectoryData(self, url, nextViewMode, currentViewMode):
		printl("", self, "S")
		# For Jellyfin treat as generic Items call
		printl("", self, "C")
		return self.getMediaData(url, None, nextViewMode, currentViewMode)

	def getPartAndMediaDataFromEntry(self, entry):
		printl("", self, "S")
		# In Jellyfin, the media info is part of the item via MediaSources
		# Return the item itself
		printl("", self, "C")
		return None

	def setIpData(self):
		printl("", self, "S")
		
		# This would be implemented to set IP data
		
		printl("", self, "C")

	def setMyPlexData(self):
		printl("", self, "S")
		
		# This would be implemented to set MyPlex data
		
		printl("", self, "C")

	def prepareServerDict(self, resolvedMyPlexAddress, machineIdentifier):
		printl("", self, "S")
		
		# This would be implemented to prepare server dictionary
		
		printl("", self, "C")
		return {}

	def getCurrentServer(self):
		printl("", self, "S")
		
		# This would be implemented to get current server
		
		printl("", self, "C")
		return self.g_currentServer

	def setAccessTokenHeader(self, address, accessToken, serverVersion=None):
		printl("", self, "S")

		# Memorizza server corrente e token
		self.g_currentServer = address
		self.g_accessToken = accessToken
		self.g_sessionID = accessToken

		# Prepara header per richieste successive
		try:
			from .JellyfinSettings import JellyfinSettingsFactory
			self.g_headers = JellyfinSettingsFactory().createHeader(self.g_sessionID, asDict=True)
		except Exception:
			# Fallback minimale
			self.g_headers = {
				'Accept': 'application/json',
				'Content-Type': 'application/json',
				'Authorization': buildAuthorizationHeaderValue(accessToken)
			}

		# Aggiorna dizionario server
		if isinstance(self.g_serverDict, dict):
			if address not in self.g_serverDict:
				self.g_serverDict[address] = {}
			self.g_serverDict[address]['token'] = accessToken
			if serverVersion is not None:
				self.g_serverDict[address]['serverVersion'] = serverVersion

		printl("", self, "C")

	def leaveOnError(self):
		printl("", self, "S")
		
		# This would be implemented to handle leaving on error
		
		printl("", self, "C")
		return False

	def loadSectionCache(self):
		printl("", self, "S")
		
		# This would be implemented to load section cache
		
		printl("", self, "C")

	def saveSectionCache(self):
		printl("", self, "S")
		
		# This would be implemented to save section cache
		
		printl("", self, "C")

	def updateSectionCache(self, entryData):
		printl("", self, "S")
		
		# This would be implemented to update section cache
		
		printl("", self, "C")

	def getAllSectionsXmlTree(self):
		printl("", self, "S")
		
		# This would be implemented to get all sections XML tree
		
		printl("", self, "C")
		return None

	# Jellyfin has no "shared home user" concept (see
	# AbstractServerSettings.getUserSwitchMode() - Jellyfin declares
	# USER_SWITCH_LOCAL_PROFILES instead), so DP_ServerMenu never actually
	# calls these four for a Jellyfin server; they exist only because
	# DP_MediaLibrary is an ABC and every backend must implement every
	# abstract method.
	def getSharedServerForUser(self):
		return []

	def getAlternateUsers(self):
		return []

	def switchUser(self, userId, pin):
		return False

	def getUserTokenForLocalServerAuthentication(self, ipInConfig):
		return None

	def getContextSubtitleStreams(self, context):
		if isinstance(context, dict):
			return context.get('subtitleStreams')
		return None

	def getContextAudioStreams(self, context):
		if isinstance(context, dict):
			return context.get('audioStreams')
		return None

	def getRemoteClientIdentifierHeaderNames(self):
		return ['X-Emby-Token', 'X-MediaBrowser-Token']

	def getRemotePollHeaders(self, commandID):
		return {
			'Access-Control-Expose-Headers': 'X-Emby-Token',
			'Content-Type': 'application/json',
		}

	def getRemoteResourceDescriptor(self, boxName):
		import json
		jsonData = {
			"DeviceId": getUUID(),
			"DeviceName": boxName,
			"AppName": "DreamPlex",
			"AppVersion": getVersion(),
			"DeviceVersion": getVersion(),
			"IconUrl": "",
			"Capabilities": {
				"PlayableMediaTypes": ["Video", "Audio", "Photo"],
				"SupportedCommands": ["Play", "Pause", "Stop", "Next", "Previous"],
				"SupportsMediaControl": True,
				"SupportsContentUploading": False,
				"SupportsPersistentIdentifier": True,
			},
		}
		return json.dumps(jsonData)

	def getRemoteContentType(self):
		return 'application/json; charset="utf-8"'

	def getRemoteAccessControlHeaders(self):
		return {
			'X-Emby-Token': getUUID(),
			'Access-Control-Max-Age': '1209600',
			'Access-Control-Allow-Credentials': 'true',
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
			'Access-Control-Allow-Headers': 'x-emby-authorization,x-mediabrowser-token,x-emby-token',
		}

	def getContentUrl(self, address, path):
		printl("", self, "S")
		# Build a full URL out of a relative path for Jellyfin
		full = self._build_url(path, add_token=False)
		printl("", self, "C")
		return full

	def getAuthDetails(self, details, url_format=True, prefix="&"):
		printl("", self, "S")
		# For Jellyfin we can return api_key query parameter if needed
		token = self._token()
		if not token:
			return ""
		if url_format:
			return f"{prefix}api_key={token}"
		return token
		printl("", self, "C")
		return ""

	def getNewMyPlexToken(self):
		printl("", self, "S")
		
		# This would be implemented to get new MyPlex token
		
		printl("", self, "C")
		return None

	def getLastResponse(self):
		printl("", self, "S")
		
		# This would be implemented to get last response
		
		printl("", self, "C")
		return self.g_lastResponse

	def doRequest(self, url, myType="GET"):
		printl("", self, "S")
		# Generic HTTP request helper; accepts full or relative URL. This
		# does its OWN fetch rather than delegating to _request_json(): that
		# helper always tries body.decode('utf-8') + json.loads() and
		# returns None the moment either fails - fine for the JSON API
		# calls it exists for, but it silently discarded every binary
		# response (poster/backdrop image downloads) a caller here needed
		# raw bytes from. DP_Player.downloadPoster()/
		# _loadSimilarSuggestionPoster() and DP_ServerMenu._loadHeroPoster()
		# all call this expecting the actual image bytes to write to disk -
		# they got None every time for any Jellyfin image never cached
		# before, a real, pre-existing bug this uncovered, not something
		# specific to the hero banner.
		method = myType.upper()
		data = b"" if method in ("POST", "PUT", "DELETE") else None
		fullUrl = self._build_url(url)
		self.g_lastUrl = fullUrl
		headers = getattr(self, 'g_headers', None) or {}
		req = Request(fullUrl, data=data, headers=headers)
		req.get_method = lambda: method
		try:
			resp = urlopen(req, timeout=self.g_connectionTimeout)
			body = resp.read()
			self.g_lastResponse = body
			self.g_currentError = ""
			printl("", self, "C")
			return body
		except Exception as e:
			self.g_lastError = str(e)
			self.g_currentError = str(e)
			printl("", self, "C")
			return None

	def refreshLibrarySection(self, token):
		printl("", self, "S")

		# token is the library section's (or "By Folder" sub-folder's) own
		# item id, threaded in by getMediaData() -> _to_entry() for every
		# row of that listing (see there) - same shape as Plex's own
		# context['libraryRefreshURL'], just an id instead of a ready-made
		# URL, since Jellyfin's refresh is a POST to a per-item endpoint
		# rather than a GET on a section-specific one.
		if token:
			try:
				self._request_json("POST", f"/Items/{token}/Refresh", params={
					"Recursive": "true",
					"MetadataRefreshMode": "Default",
					"ImageRefreshMode": "Default",
					"ReplaceAllMetadata": "false",
					"ReplaceAllImages": "false",
				})
			except Exception as e:
				printl("could not refresh library section: " + str(e), self, "W")

		printl("", self, "C")

	def mediaType(self, partData, server):
		printl("", self, "S")
		# getMediaOptionsToPlay() already built the fully-resolved stream URL
		# (token + audio/subtitle/quality overrides) into options[0][1], which
		# DP_Player.setSelectedMedia() passes in here as partData['file'] -
		# nothing left to resolve.
		url = partData.get('file') if isinstance(partData, dict) else None
		printl("", self, "C")
		return url

	def checkFileLocation(self, remotePathPart, localPathPart):
		printl("", self, "S")
		
		# This would be implemented to check file location
		
		printl("", self, "C")
		return None

	def getStreamDataById(self, server, myId, loadExtraData=False):
		printl("", self, "S")
		# Return MediaSources for an item
		user_id = self._user_id()
		if not myId or not user_id:
			printl("Missing id/user", self, "E")
			return None
		data = self._request_json("GET", f"/Users/{user_id}/Items/{myId}", params={"Fields": "MediaSources,Path"})
		printl("", self, "C")
		return data
		
		printl("", self, "C")
		return None

	def getSelectedSubtitleDataById(self, server, myId, forcedOnly=False):
		printl("", self, "S")
		info = self.getSubtitlesById(server, myId) or {}
		subs = []
		for s in info.get('MediaStreams', []) or []:
			if s.get('Type') == 'Subtitle':
				if forcedOnly and not s.get('IsForced'):
					continue
				subs.append(s)
		printl("", self, "C")
		return subs

	def getSubtitlesById(self, server, myId):
		printl("", self, "S")
		user_id = self._user_id()
		if not myId or not user_id:
			return None
		data = self._request_json("GET", f"/Users/{user_id}/Items/{myId}", params={"Fields": "MediaStreams"})
		printl("", self, "C")
		return data

	def getAudioById(self, server, myId):
		printl("", self, "S")
		user_id = self._user_id()
		if not myId or not user_id:
			return None
		data = self._request_json("GET", f"/Users/{user_id}/Items/{myId}", params={"Fields": "MediaStreams"})
		printl("", self, "C")
		return data

	def setSubtitleById(self, server, sub_id, part_id):
		printl("", self, "S")
		# In Jellyfin usually selection is done via stream query during playback; keep as no-op
		printl("", self, "C")
		return None

	def setAudioById(self, server, audio_id, part_id):
		printl("", self, "S")
		# In Jellyfin selection can be passed via AudioStreamIndex; keep as no-op
		printl("", self, "C")
		return None

	def getExtraData(self, server, myId, myType, loadExtraData):
		printl("", self, "S")
		
		# This would be implemented to get extra data
		
		printl("", self, "C")
		return None

	def getAudioSubtitlesMedia(self, server, myId, myType, loadExtraData):
		printl("", self, "S")
		# Return combined audio/subtitle tracks info
		info = self._request_json("GET", f"/Users/{self._user_id()}/Items/{myId}", params={"Fields": "MediaStreams"})
		printl("", self, "C")
		return info

	def getSelectedEmbeddedSubtitleData(self):
		# Set by _pick_stream_indices(), called from getMediaOptionsToPlay()
		# just before this - see the comment there.
		return self.g_SelectedEmbeddedSubtitleData

	def getMediaOptionsToPlay(self, myId, vids, override=False, myType="Video", loadExtraData=False):
		printl("", self, "S")
		# Costruisci URL di playback diretto includendo indici audio/sottotitoli e qualità
		if not myId:
			return 0, [], ''
		# Leggi override degli indici se presenti in vids
		aidx_override = None
		sidx_override = None
		try:
			if isinstance(vids, dict):
				if 'audioIndex' in vids:
					aidx_override = int(vids.get('audioIndex'))
				if 'subtitleIndex' in vids:
					sidx_override = int(vids.get('subtitleIndex'))
			# If not present in vids, try the temporary overrides from settings
			if aidx_override is None:
				try:
					oa = int(self.g_serverConfig._overrideAudioIndex.getValue())
					if oa is not None and oa >= 0:
						aidx_override = oa
				except Exception:
					pass
			if sidx_override is None:
				try:
					osub = int(self.g_serverConfig._overrideSubtitleIndex.getValue())
					if osub is not None and osub >= 0:
						sidx_override = osub
				except Exception:
					pass
		except Exception:
			pass
		params = self._stream_params(myId, direct=True, aidx_override=aidx_override, sidx_override=sidx_override)
		direct_url = self._build_url(f"/Videos/{myId}/stream", params=params, add_token=True)

		# Reset the temporary overrides after use
		try:
			changed = False
			if aidx_override is not None and hasattr(self.g_serverConfig, '_overrideAudioIndex'):
				self.g_serverConfig._overrideAudioIndex.setValue(-1)
				changed = True
			if sidx_override is not None and hasattr(self.g_serverConfig, '_overrideSubtitleIndex'):
				self.g_serverConfig._overrideSubtitleIndex.setValue(-1)
				changed = True
			if changed:
				self.g_serverConfig._settings.writeToFile()
		except Exception:
			pass

		# DP_Player.buildPlayerData()/selectMedia() unpack this as
		# (count, options, server) and, when count == 1, read
		# options[0][0]/options[0][1] straight through into mediaType() -
		# returning the {'id','url','token'} dict used here before crashed
		# with "cannot unpack non-iterable dict" the instant a movie was
		# selected. Jellyfin has no Plex-style multi-part media, so count is
		# always 1; direct_url is already fully built with the audio/
		# subtitle/quality overrides above, so mediaType() below just has to
		# hand it back unchanged.
		options = [(myId, direct_url, None, None, None)]
		printl("", self, "C")
		return 1, options, ''

	def playLibraryMedia(self, myId, url, isExtraData=False):
		printl("", self, "S")
		# Restituisce URL riproducibile applicando preferenze audio/sottotitoli
		if url and url.startswith("http"):
			playable = url
		else:
			params = self._stream_params(myId, direct=True)
			playable = self._build_url(url or f"/Videos/{myId}/stream", params=params, add_token=True)

		# DP_Player.setPlayerData() indexes this return value directly as a
		# dict (playbackData['resumeStamp']/['server']/['videoData']['title']/
		# ...), never through .get() - the plain URL string returned here
		# before crashed with "string indices must be integers" the instant
		# playback was attempted. Mirrors DP_PlexLibrary.playLibraryMedia()'s
		# playerData shape; fields Jellyfin has no equivalent for (multi-user
		# server, transcoding session, local-file subtitle handling) are left
		# at harmless defaults.
		item = {}
		user_id = self._user_id()
		if user_id and myId:
			item = self._request_json("GET", f"/Users/{user_id}/Items/{myId}", params={"Fields": "Overview,Genres,People,ProductionYear,OfficialRating,CommunityRating,RunTimeTicks"}) or {}
		userData = item.get('UserData') or {}
		resumeStamp = self._jellyfin_ticks_to_ms(userData.get('PlaybackPositionTicks') or 0)

		# same People-splitting logic as _to_entry() - kept in sync with what
		# the info panel (DP_Player's INFO key) actually expects to read
		people = item.get('People') or []
		directors = [p.get('Name') for p in people if p.get('Type') == 'Director']
		actors = [p.get('Name') for p in people if p.get('Type') == 'Actor']

		videoData = {
			'title': item.get('Name') or '',
			'summary': item.get('Overview') or '',
			'genre': ', '.join(item.get('Genres') or []),
			'director': ', '.join(directors),
			'cast': ', '.join(actors),
			'year': item.get('ProductionYear') or '',
			'contentRating': item.get('OfficialRating') or '',
			'rating': item.get('CommunityRating') or 0,
			'duration': self._jellyfin_ticks_to_ms(item.get('RunTimeTicks') or 0),
			'isFavorite': bool(userData.get('IsFavorite')),
		}

		playerData = {
			'playUrl': playable,
			'resumeStamp': resumeStamp,
			'server': '',
			'id': myId,
			'multiUserServer': False,
			'playbackType': str(self.g_serverConfig._playbackType.getValue()),
			'connectionType': str(self.g_serverConfig._connectionType.getValue()),
			'localAuth': bool(self.g_serverConfig._localAuth.getValue()),
			'transcodingSession': '',
			'videoData': videoData,
			'mediaData': {},
			'usingExtForcedSubs': False,
			'fallback': None,
			'locations': [],
			'currentFile': None,
			'subtitleFileTemp': None,
			'universalTranscoder': bool(self.g_serverConfig._universalTranscoder.getValue()),
		}
		printl("", self, "C")
		return playerData

	def reportPlaybackProgress(self, server, itemId, currentTimeSec, totalTimeSec, stopped=False):
		"""Tells the Jellyfin server where playback stopped, so it can update
		the resume position and (if far enough into the item) mark it played.
		`server` is part of the shared DP_MediaLibrary interface (Plex needs
		it, this backend already knows its own base URL) and is unused here.

		Called by DP_Player.handleProgress() at the same points regardless
		of which backend is active - not on a periodic tick, so no
		PlaySessionId needs to be kept consistent across calls; a fresh one
		per call is accepted by the server the same way. Uses the documented
		PlaystateController endpoints (POST /Sessions/Playing/Progress,
		/Sessions/Playing/Stopped) rather than a lower-level per-item
		UserData write, since that is what actually drives Jellyfin's own
		"Continue Watching"/watched-state logic on the server side.
		"""
		printl("", self, "S")

		if not itemId or currentTimeSec <= 0:
			printl("", self, "C")
			return

		try:
			positionTicks = int(max(0, currentTimeSec) * 10_000_000)
			payload = {
				"ItemId": str(itemId),
				"PositionTicks": positionTicks,
				"PlaySessionId": uuid.uuid4().hex,
				"IsPaused": False,
			}
			path = "/Sessions/Playing/Stopped" if stopped else "/Sessions/Playing/Progress"
			self._request_json("POST", path, data=json.dumps(payload).encode('utf-8'))
		except Exception as e:
			printl("could not report playback progress: " + str(e), self, "W")

		printl("", self, "C")

	def getSimilarItems(self, server, itemId, limit=6):
		"""Suggested titles for the "you might also like" carousel near the
		end of a standalone movie (DP_Player has no next playlist entry to
		offer there, unlike a show). Uses Jellyfin's own /Items/{id}/Similar
		endpoint - server-side, so it already accounts for genre/people/tags
		the way Jellyfin's own UI does, rather than reimplementing that
		matching here. `server` is Plex-only, unused here (same as
		reportPlaybackProgress()).
		"""
		printl("", self, "S")

		if not itemId:
			printl("", self, "C")
			return []

		try:
			user_id = self._user_id()
			params = {"Limit": limit, "Fields": "Overview,Genres,People,ProductionYear,OfficialRating,CommunityRating,RunTimeTicks"}
			if user_id:
				params["UserId"] = user_id
			result = self._request_json("GET", f"/Items/{itemId}/Similar", params=params) or {}
			items = result.get("Items") or []
			entries = [self._to_entry(item) for item in items]
		except Exception as e:
			printl("could not fetch similar-title suggestions: " + str(e), self, "W")
			printl("", self, "C")
			return []

		printl("", self, "C")
		return entries

	def _fetchHeroBucket(self, path, limit, heroKind, user_id):
		"""One hero bucket (see getHeroSuggestions()) - path is one of
		Jellyfin's own endpoints ("Items/Resume", "Items/Latest"), heroKind
		tags every entryData so DP_ServerMenu can show a "Continue"/
		"Suggested" badge on the hero banner."""
		params = {"Limit": limit, "Fields": "Overview,Genres,ProductionYear,OfficialRating,CommunityRating,RunTimeTicks"}
		items = self._request_json("GET", f"/Users/{user_id}/{path}", params=params) or []
		# /Items/Latest returns a bare list, /Items/Resume a {"Items": [...]}
		# envelope like every other Items query - same asymmetry the "Latest"
		# fetch already had to handle before this bucket was split out.
		if isinstance(items, dict):
			items = items.get("Items") or []
		entries = []
		for item in items:
			title, entryData, contextMenu, viewState, nextUrl = self._to_entry(item)
			entryData['heroKind'] = heroKind
			entries.append((title, entryData, contextMenu, viewState, nextUrl))
		return entries

	def getHeroSuggestions(self, limit=6):
		"""Jellyfin's own "Continue Watching" (Resume) endpoint for the
		"continue" bucket, and "Latest" (recently added, its existing
		fetch) for "suggested" once Resume runs out of items - the concrete
		fetch behind DP_MediaLibrary.getHeroSuggestions() (see there for why
		this is its own method rather than something DP_MainMenu calls
		directly)."""
		printl("", self, "S")

		user_id = self._user_id()
		if not user_id:
			printl("", self, "C")
			return []

		try:
			entries = self._fetchHeroBucket("Items/Resume", limit, "continue", user_id)
			if len(entries) < limit:
				seenIds = {e[1].get('id') for e in entries}
				for entry in self._fetchHeroBucket("Items/Latest", limit - len(entries), "suggested", user_id):
					if entry[1].get('id') not in seenIds:
						entries.append(entry)
		except Exception as e:
			printl("could not fetch hero suggestions: " + str(e), self, "W")
			printl("", self, "C")
			return []

		printl("", self, "C")
		return entries

	def getRatingKind(self) -> str:
		return RATING_KIND_FAVORITE

	def submitRating(self, server, itemId, value):
		self.setFavorite(itemId, bool(value))

	def setFavorite(self, itemId, favorite):
		"""Marks/unmarks an item as favorite - Jellyfin's API dropped the
		personal star rating Plex has, so the FAV-key rating panel offers a
		favorite toggle here instead of the 5-star scale used for Plex."""
		printl("", self, "S")

		user_id = self._user_id()
		if not user_id or not itemId:
			printl("", self, "C")
			return

		method = "POST" if favorite else "DELETE"
		try:
			self._request_json(method, f"/Users/{user_id}/FavoriteItems/{itemId}")
		except Exception as e:
			printl("could not set favorite: " + str(e), self, "W")

		printl("", self, "C")

	def setAudioSubtitles(self, stream):
		printl("", self, "S")
		
		# This would be implemented to set audio subtitles
		
		printl("", self, "C")
		return None

	def getXmlTreeFromPlex(self, url, requestType="GET"):
		printl("", self, "S")
		
		# This would be implemented to get XML tree from Plex
		
		printl("", self, "C")
		return None

	def getXmlTreeFromUrl(self, url):
		printl("", self, "S")
		
		# This would be implemented to get XML tree from URL
		
		printl("", self, "C")
		return None

	def getFakeXml(self):
		printl("", self, "S")
		
		# This would be implemented to get fake XML
		
		printl("", self, "C")
		return None

	def sessionID(self):
		printl("", self, "S")
		
		# This would be implemented to get session ID
		
		printl("", self, "C")
		return self.g_sessionID

	def getLastErrorMessage(self):
		printl("", self, "S")
		
		# This would be implemented to get last error message
		
		printl("", self, "C")
		return self.g_currentError

	def getListFromTag(self, entry, tagName):
		printl("", self, "S")
		
		# This would be implemented to get list from tag
		
		printl("", self, "C")
		return []

	def getImage(self, data, server, myType, transcode=True):
		printl("", self, "S")
		# data may contain item dict or id
		item_id = None
		if isinstance(data, dict):
			item_id = data.get('Id') or data.get('id')
		else:
			item_id = str(data)
		if not item_id:
			printl("", self, "C")
			return None
		url = self._build_url(f"/Items/{item_id}/Images/Primary", params={"maxWidth": 600, "maxHeight": 900}, add_token=True)
		printl("", self, "C")
		return url

	def photoTranscode(self, server, url, width=999, height=999):
		printl("", self, "S")
		# Return URL with size parameters
		full = self._build_url(url, params={"maxWidth": width, "maxHeight": height}, add_token=True)
		printl("", self, "C")
		return full

	def watched(self, url):
		printl("", self, "S")
		# Mark played: POST /Users/{userId}/PlayedItems/{id}
		user_id = self._user_id()
		item_id = str(url).split("/")[-1]
		if user_id and item_id:
			self._request_json("POST", f"/Users/{user_id}/PlayedItems/{item_id}")
		printl("", self, "C")
		return None

	def deleteMedia(self, url):
		printl("", self, "S")
		# Jellyfin supports DELETE /Items/{Id} if enabled
		item_id = str(url).split("/")[-1]
		if item_id:
			self._request_json("DELETE", f"/Items/{item_id}")
		printl("", self, "C")
		return None

	def buildContextMenu(self, url, ratingKey, server):
		printl("", self, "S")
		context = {}

		try:
			user_id = self._user_id()
			item_id = ratingKey or (str(url).split("/")[-1] if url else None)
			# Mark as watched / unwatched
			if user_id and item_id:
				context['watchedURL'] = f"/Users/{user_id}/PlayedItems/{item_id}"
				context['watchedMethod'] = 'POST'
				context['unwatchURL'] = f"/Users/{user_id}/PlayedItems/{item_id}"
				context['unwatchMethod'] = 'DELETE'
			# Delete item
			if item_id:
				context['deleteURL'] = f"/Items/{item_id}"
				context['deleteMethod'] = 'DELETE'

			# Audio/Sub streams for manual selection
			streams_info = self._request_json("GET", f"/Users/{user_id}/Items/{item_id}", params={"Fields": "MediaStreams"}) if (user_id and item_id) else None
			audio_list = []
			sub_list = []
			if streams_info and isinstance(streams_info, dict):
				for s in streams_info.get('MediaStreams', []) or []:
					if s.get('Type') == 'Audio':
						audio_list.append({
							'index': s.get('Index'),
							'language': s.get('Language'),
							'codec': s.get('Codec'),
							'channels': s.get('Channels')
						})
					elif s.get('Type') == 'Subtitle':
						sub_list.append({
							'index': s.get('Index'),
							'language': s.get('Language'),
							'codec': s.get('Codec'),
							'isForced': s.get('IsForced'),
							'isExternal': s.get('IsExternal')
						})
			if audio_list:
				context['audioStreams'] = audio_list
			if sub_list:
				context['subtitleStreams'] = sub_list
		except Exception as e:
			self.g_lastError = str(e)

		printl("", self, "C")
		return context

	def getUrlPathFormURL(self, url):
		printl("", self, "S")
		try:
			from urllib.parse import urlparse
			return urlparse(url).path
		except Exception:
			return url
		printl("", self, "C")
		return ""

	def getServerFromURL(self, url) -> str:
		printl("", self, "S")
		try:
			from urllib.parse import urlparse
			o = urlparse(url)
			return f"{o.scheme}://{o.netloc}"
		except Exception:
			return self.g_serverUrl or ""
		printl("", self, "C")
		return ""

	def getLinkURL(self, url, pathData, server):
		printl("", self, "S")
		return self._build_url(url, add_token=True)
		printl("", self, "C")
		return ""

	def getTranscodeSettings(self, override=False):
		printl("", self, "S")
		# Baseline qualità/transcode parametrizzati dal setting qualità
		max_bitrate = self._map_quality_to_bitrate()
		# AudioBitrate indicativo (10% del video, minimo 96k, massimo 384k)
		audio_bitrate = max(96_000, min(384_000, int(max_bitrate * 0.1)))
		settings = {
			'MaxStreamingBitrate': max_bitrate,
			'AudioBitrate': audio_bitrate,
			'TranscodingContainer': 'ts',
			'VideoCodec': 'h264',
			'AudioCodec': 'aac'
		}
		printl("", self, "C")
		return settings

	def get_hTokenForServer(self, server) -> dict[str, str]:
		printl("", self, "S")
		# Return headers containing token
		token = self._token()
		headers = getattr(self, 'g_headers', None) or {}
		if token and 'Authorization' not in headers:
			headers['Authorization'] = buildAuthorizationHeaderValue(token)
		printl("", self, "C")
		return headers

	def get_aTokenForServer(self, server):
		printl("", self, "S")
		token = self._token()
		printl("", self, "C")
		return token or ""

	def get_uTokenForServer(self, server):
		printl("", self, "S")
		return self._user_id() or ""
		printl("", self, "C")
		return ""

	def getServerName(self):
		printl("", self, "S")
		name = None
		try:
			name = self.g_serverConfig._name.getValue()
		except Exception:
			name = "Jellyfin"
		printl("", self, "C")
		return name or "Jellyfin"

	def setServerDetails(self):
		printl("", self, "S")
		
		if self.g_serverConfig is not None:
			self.serverConfig_connectionType = self.g_serverConfig._connectionType.getValue()
			self.serverConfig_port = self.g_serverConfig._port.getValue()
			self.serverConfig_localAuth = self.g_serverConfig._localAuth.getValue()
			
			if self.serverConfig_connectionType == "0": # IP
				ipval = self.g_serverConfig._ip.getValue()
				if isinstance(ipval, (list, tuple)) and len(ipval) == 4:
					self.g_host = ".".join(str(x) for x in ipval)
				else:
					self.g_host = str(ipval)
			else: # DNS
				self.g_host = self.g_serverConfig._dns.getValue()
				
			self.g_serverUrl = "http://" + self.g_host + ":" + str(self.serverConfig_port)
		
		printl("", self, "C")

	def getUniversalTranscoderSettings(self):
		printl("", self, "S")
		
		# This would be implemented to get universal transcoder settings
		
		printl("", self, "C")
		return {}

	def transcode(self, myID, url):
		printl("", self, "S")
		# Costruisci URL HLS includendo qualità e selezione audio/sottotitoli
		params = self._stream_params(myID, direct=False)
		hls = self._build_url(f"/Videos/{myID}/master.m3u8", params=params, add_token=True)
		printl("", self, "C")
		return hls

	def getFullListEntry(self, entryData, url, viewState=None, isDirectory=False):
		printl("", self, "S")
		# Normalize a Jellyfin item into a common entry dict
		if not isinstance(entryData, dict):
			return {}
		entry = {
			'id': entryData.get('Id'),
			'title': entryData.get('Name'),
			'type': entryData.get('Type'),
			'overview': entryData.get('Overview'),
			'image': self.getImage(entryData, None, None),
			'url': url
		}
		printl("", self, "C")
		return entry

	def getViewStateForShowEntry(self, entryData):
		printl("", self, "S")
		# Not critical for Jellyfin minimal implementation
		printl("", self, "C")
		return None

	def getViewStatefromViewCount(self, entryData):
		printl("", self, "S")
		# Not critical for Jellyfin minimal implementation
		printl("", self, "C")
		return None

	def getServerConfig(self):
		printl("", self, "S")
		
		printl("", self, "C")
		return self.g_serverConfig

	# -------------------------------------------------
	# Internal conversion helpers
	# -------------------------------------------------

	# Leaf item types are directly playable - everything else is a container
	# the user has to drill into further. DP_View.onEnter() branches on
	# entryData['tagType']: "Track"/"Video" opens DP_Player, anything else
	# calls self._load(entryData) again with entryData['nextViewMode'] as the
	# next fetch mode - _CONTAINER_NEXT_VIEW_MODE is the map from a Jellyfin
	# container Type to the nextViewMode string DP_LibMain.
	# getLibraryDataFromPlex() dispatches on.
	_LEAF_TAG_TYPES = {'Movie': 'Video', 'Episode': 'Video', 'Audio': 'Track'}
	_CONTAINER_NEXT_VIEW_MODE = {
		'Series': 'ShowSeasons',
		'Season': 'ShowEpisodes',
		'MusicArtist': 'ShowAlbums',
		'MusicAlbum': 'ShowTracks',
	}
	# entryData['type'] for a leaf item only ever gets read by DP_ViewMixed
	# (Collections/Playlists rows, see _collectionsAndPlaylistsEntries()) -
	# it was designed for Plex, whose own API already returns "movie"/
	# "episode"/"season" lowercase, and checks it verbatim. Jellyfin's own
	# itemType is capitalized ("Movie"/"Episode"/"Season") and, before this,
	# was passed straight through unnormalized - DP_ViewMixed._refresh() has
	# no branch for the literal capitalized strings and crashed the moment
	# any Jellyfin content (a movie inside a Collection, in particular)
	# actually flowed through it for the first time.
	_LEAF_TYPE_TO_PLEX_STYLE = {'Movie': 'movie', 'Episode': 'episode', 'Season': 'season'}

	def _jellyfin_ticks_to_ms(self, ticks) -> int:
		# Jellyfin timestamps are in 100ns ticks; durationToTime() (__common__.
		# py) expects milliseconds like Plex's XML "duration" attribute does.
		try:
			return int(ticks) // 10000
		except Exception:
			return 0

	def _build_media_data_arr(self, item: dict) -> list:
		# DP_ViewMovies._refresh() unconditionally does
		# self.details["mediaDataArr"][0]["Parts"][0] - this reproduces just
		# enough of Plex's XML-derived shape (videoCodec/audioCodec/
		# videoFrameRate/audioChannels/aspectRatio/videoResolution/Parts[0].
		# file) from Jellyfin's MediaStreams/MediaSources for that access, and
		# for the handle*Pixmaps() codec/resolution/channel badges, to not
		# work from Jellyfin's raw values.
		mediaSources = item.get('MediaSources') or []
		path = item.get('Path') or (mediaSources[0].get('Path') if mediaSources else '') or ''
		streams = item.get('MediaStreams') or (mediaSources[0].get('MediaStreams') if mediaSources else []) or []
		videoStream = next((s for s in streams if s.get('Type') == 'Video'), {})
		audioStream = next((s for s in streams if s.get('Type') == 'Audio'), {})

		height = videoStream.get('Height') or 0
		if height >= 2000:
			resolution = "2160"
		elif height >= 1000:
			resolution = "1080"
		elif height >= 700:
			resolution = "720"
		elif height:
			resolution = "480"
		else:
			resolution = ""

		aspect = ""
		rawAspect = videoStream.get('AspectRatio') or ''
		if ':' in rawAspect:
			try:
				w, h = rawAspect.split(':')
				aspect = "%.2f" % (float(w) / float(h))
			except Exception:
				aspect = ""

		bitRate = videoStream.get('BitRate')
		mediaData = {
			'videoCodec': (videoStream.get('Codec') or '').upper(),
			'audioCodec': (audioStream.get('Codec') or '').upper(),
			'videoFrameRate': str(videoStream.get('AverageFrameRate') or videoStream.get('RealFrameRate') or ''),
			'audioChannels': str(audioStream.get('Channels') or ''),
			'aspectRatio': aspect,
			'videoResolution': resolution,
			'bitrate': str(int(bitRate / 1000)) if bitRate else '',
			'Parts': [{'file': path}],
		}
		return [mediaData]

	def _to_entry(self, item: dict, currentViewMode: str = '', refreshParentId: str = None) -> tuple:
		# Builds the same 5-tuple shape DP_PlexLibrary.getFullListEntry()
		# returns - (title, entryData, contextMenu, viewState, nextUrl) - that
		# DP_View/alterViewStateInList()/onEnter() index into directly
		# (listViewEntry[3] for viewState, selection[4] as the next
		# contentUrl, ...). A bare dict here (the previous shape) crashed
		# with KeyError: 3 the moment a list actually rendered.
		itemType = item.get('Type')
		itemId = item.get('Id')

		# "By Folder" browsing (getMediaData with recursive=False) mixes real
		# sub-folders in with playable files at the same level. A folder is
		# not itself a Series/MusicArtist/etc container, so it would
		# otherwise fall through as an (unplayable) leaf - tag it "Directory"
		# instead, same as Plex's own filesystem-folder rows, so DP_View
		# treats it as something to descend into (self.type == "Folder" also
		# drives the folder icon/hidden-refresh-button behaviour in
		# DP_View.refresh()).
		# BoxSet (Collection) and Playlist rows (see
		# _collectionsAndPlaylistsEntries()) are always containers to
		# descend into, regardless of what IsFolder says - it is not
		# reliably true for them across Jellyfin server versions, and
		# without this they fell through as an (unplayable, crashing) leaf
		# with the literal itemType as their "type", which nothing renders.
		isFolder = itemType in ('BoxSet', 'Playlist') or (bool(item.get('IsFolder')) and itemType not in self._CONTAINER_NEXT_VIEW_MODE and itemType not in self._LEAF_TAG_TYPES)
		if isFolder:
			tagType = 'Directory'
			isLeaf = False
		else:
			tagType = self._LEAF_TAG_TYPES.get(itemType, itemType)
			isLeaf = itemType in self._LEAF_TAG_TYPES

		userData = item.get('UserData') or {}
		if userData.get('Played'):
			viewState = 'seen'
		elif (userData.get('PlaybackPositionTicks') or 0) > 0:
			viewState = 'started'
		else:
			viewState = 'unseen'

		people = item.get('People') or []
		directors = [p.get('Name') for p in people if p.get('Type') == 'Director']
		writers = [p.get('Name') for p in people if p.get('Type') == 'Writer']
		actors = [p.get('Name') for p in people if p.get('Type') == 'Actor']

		thumb = self.getImage(item, None, None) or ''
		art = ''
		if itemId:
			art = self._build_url(f"/Items/{itemId}/Images/Backdrop/0", params={"maxWidth": 1920}, add_token=True)

		# DP_ViewShows._refresh() does int(self.details.get("leafCount", " "))
		# - int(self.details.get("viewedLeafCount", " ")) unconditionally for
		# a Series/Season row, with no try/except: a missing key silently
		# defaults to " " (via .get()'s fallback) and int(" ") crashes. Plex
		# gives leafCount/viewedLeafCount directly off its XML; the Jellyfin
		# equivalents are RecursiveItemCount (total episodes, Series) or
		# ChildCount (episodes in a Season) and UserData.UnplayedItemCount.
		childCount = item.get('ChildCount')
		leafCount = item.get('RecursiveItemCount')
		if leafCount is None:
			leafCount = childCount if childCount is not None else 0
		unplayedCount = userData.get('UnplayedItemCount')
		if unplayedCount is None:
			viewedLeafCount = leafCount if userData.get('Played') else 0
		else:
			viewedLeafCount = max(0, leafCount - unplayedCount)

		entryData = {
			'id': itemId,
			'Id': itemId,
			'ratingKey': itemId,
			'title': item.get('Name') or '',
			'tagline': '',
			'summary': item.get('Overview') or '',
			'overview': item.get('Overview') or '',
			'cast': ', '.join(actors),
			'writer': ', '.join(writers),
			'director': ', '.join(directors),
			'studio': ', '.join(s.get('Name', '') for s in (item.get('Studios') or [])),
			'genre': ', '.join(item.get('Genres') or []),
			'year': item.get('ProductionYear') or '',
			'contentRating': item.get('OfficialRating') or '',
			'rating': item.get('CommunityRating') or 0,
			'duration': self._jellyfin_ticks_to_ms(item.get('RunTimeTicks') or 0),
			'type': 'Folder' if isFolder else self._LEAF_TYPE_TO_PLEX_STYLE.get(itemType, itemType or item.get('CollectionType')),
			'tagType': tagType,
			'server': '',
			'currentViewMode': currentViewMode,
			'nextViewMode': 'ShowDirectory' if isFolder else self._CONTAINER_NEXT_VIEW_MODE.get(itemType, currentViewMode),
			'thumb': thumb,
			'art': art,
			'mediaDataArr': self._build_media_data_arr(item) if isLeaf else [{'Parts': [{'file': ''}]}],
			'raw': item,
			'leafCount': leafCount,
			'viewedLeafCount': viewedLeafCount,
			'childCount': childCount or 0,
			# For an Episode: parentRatingKey is its Season, grandparent* is
			# its Series - Plex's naming, kept as-is since DP_ViewShows reads
			# these keys directly. For a Series/Season row itself these are
			# harmless placeholders, never read for those currentViewModes.
			'parentIndex': item.get('ParentIndexNumber') if item.get('ParentIndexNumber') is not None else (item.get('IndexNumber') or ''),
			'grandparentTitle': item.get('SeriesName') or '',
			'grandparentRatingKey': item.get('SeriesId') or '',
			'parentRatingKey': item.get('SeasonId') or item.get('ParentId') or '',
		}
		if not isLeaf:
			# DP_LibMain.getLibraryData()'s disk cache is keyed on
			# "<uuid>_<nextViewMode>.cache" - without a uuid per container
			# row, every folder/show/season fetched through this same
			# nextViewMode (e.g. every "ShowDirectory" sub-folder under one
			# library) collapsed onto the *same* cache file, so opening
			# folder B after folder A could silently show folder A's cached
			# listing. itemId is unique per folder/show/season, so it is what
			# gets fetched when this row is entered - reusing it as the uuid
			# gives each one its own slot.
			entryData['uuid'] = itemId
			entryData['source'] = 'jellyfin'

		title = _(entryData['title'])
		# Same key DP_PlexLibrary.buildContextMenu() uses - DP_View reads it
		# generically off context.get("libraryRefreshURL") for either
		# backend (see refreshLibrarySection()). None when the caller has
		# no section id to offer (top-level "Movies"/"Tv Shows"/"Music"
		# virtual filters span every Jellyfin library of that type at once,
		# hero/similar-suggestion rows, ...) - the refresh button then just
		# re-fetches the listing without asking the server to rescan.
		contextMenu = {'libraryRefreshURL': refreshParentId} if refreshParentId else None
		return title, entryData, contextMenu, viewState, itemId