from __future__ import annotations
from abc import ABC, abstractmethod

from Screens.Screen import Screen

# Rating capability a backend declares via getRatingKind() - DP_Player's
# FAV-key panel picks its widget (stars vs favorite toggle) from this,
# instead of checking getServerConfig().getType() against hardcoded server
# type strings. A backend with neither (or one DP_Player has no widget for
# yet) declares RATING_KIND_NONE and the FAV key does nothing for it.
RATING_KIND_NONE = "none"
RATING_KIND_FAVORITE = "favorite"
RATING_KIND_STARS = "stars"


class DP_MediaLibrary(ABC, Screen):
	def __init__(self, session):
		Screen.__init__(self, session)

	@abstractmethod
	def getRatingKind(self) -> str:
		"""One of RATING_KIND_NONE/RATING_KIND_FAVORITE/RATING_KIND_STARS -
		see the module-level constants above."""
		pass

	@abstractmethod
	def submitRating(self, server, itemId, value):
		"""value's meaning depends on getRatingKind(): a bool for
		RATING_KIND_FAVORITE, or an int 0-10 (half-star steps) / None (clear
		the rating) for RATING_KIND_STARS. `server` is Plex-only (which of
		possibly several configured servers the item lives on); Jellyfin's
		implementation ignores it, same as reportPlaybackProgress()."""
		pass

	@abstractmethod
	def reportPlaybackProgress(self, server, itemId, currentTimeSec, totalTimeSec, stopped=False):
		"""Tells the backend where playback stopped, so it can update the
		resume position and/or mark the item watched. Called by
		DP_Player.handleProgress() at the same points regardless of which
		backend is active - no server-type check needed at the call site."""
		pass

	@abstractmethod
	def getSimilarItems(self, server, itemId, limit=6):
		"""Up to `limit` suggested titles related to itemId, each in the
		same 5-tuple shape a library listing row uses (title, entryData,
		contextMenu, viewState, nextUrl - see JellyfinLibrary._to_entry()).
		Returns an empty list if nothing was found/the backend does not
		support this - never None, so callers can iterate unconditionally.
		`server` is Plex-only, same as submitRating()/
		reportPlaybackProgress(). Used by DP_Player to offer a "you might
		also like" carousel near the end of a standalone movie, the same way
		the next-episode prompt works for a show, since a movie has no next
		playlist entry of its own."""
		pass

	@abstractmethod
	def getHeroSuggestions(self, limit=6):
		"""Up to `limit` titles for the Carousel skin's rotating "hero"
		banner on the main menu (same 5-tuple shape as getSimilarItems()).
		Returns an empty list if nothing was found/the backend does not
		support this - never None.

		Two buckets, in-progress/continue-watching titles first, filled out
		with recently-added/suggested ones: each entryData carries a
		'heroKind' of 'continue' or 'suggested' so DP_ServerMenu can badge
		the hero banner accordingly.

		Deliberately its OWN abstract method rather than DP_MainMenu calling
		an existing fetch directly: today's implementation happens to just
		combine two existing fetches, backend by backend, but a future
		change to what the hero should show (e.g. weighted toward unwatched
		titles) only ever touches this one method, per backend, never the
		caller."""
		pass

	@abstractmethod
	def setPlaybackType(self, myType):
		pass

	@abstractmethod
	def getSectionTypes(self):
		pass

	@abstractmethod
	def getServerSectionPaths(self) -> list[str]:
		pass

	@abstractmethod
	def getAllSections(self, myFilter=None, serverFilterActive=False):
		pass

	@abstractmethod
	def getSectionFilter(self, incomingEntryData):
		pass

	@abstractmethod
	def getMoviesFromSection(self, url):
		pass

	@abstractmethod
	def getMixedContentFromSection(self, url, fromRemotePlayer=False):
		pass

	@abstractmethod
	def getMusicByArtist(self, url):
		pass

	@abstractmethod
	def getMusicByAlbum(self, url):
		pass

	@abstractmethod
	def getMusicTracks(self, url):
		pass

	@abstractmethod
	def getShowsFromSection(self, url):
		pass

	@abstractmethod
	def getSeasonsOfShow(self, url):
		pass

	@abstractmethod
	def getImageData(self, entryData, entry, server, switchMedias=False):
		pass


	@abstractmethod
	def getEpisodesOfSeason(self, url, directMode=False):
		pass

	@abstractmethod
	def getMediaData(self, url, tagType, nextViewMode, currentViewMode, switchMedias=False, fromRemotePlayer=False):
		pass

	@abstractmethod
	def getDirectoryData(self, url, nextViewMode, currentViewMode):
		pass

	@abstractmethod
	def getPartAndMediaDataFromEntry(self, entry):
		pass

	@abstractmethod
	def setIpData(self):
		pass

	@abstractmethod
	def setMyPlexData(self):
		pass

	@abstractmethod
	def prepareServerDict(self, resolvedMyPlexAddress, machineIdentifier):
		pass

	@abstractmethod
	def getCurrentServer(self):
		pass

	@abstractmethod
	def setAccessTokenHeader(self, address, accessToken, serverVersion=None):
		pass

	@abstractmethod
	def leaveOnError(self):
		pass

	@abstractmethod
	def loadSectionCache(self):
		pass

	@abstractmethod
	def saveSectionCache(self):
		pass

	@abstractmethod
	def updateSectionCache(self, entryData):
		pass

	@abstractmethod
	def getAllSectionsXmlTree(self):
		pass

	# Names are backend-neutral on purpose (not "...PlexUser"/"...FromPlex")
	# even though only Plex's "shared home user" model uses them today -
	# AbstractServerSettings.getUserSwitchMode() is what a caller checks to
	# know whether to call these at all (see DP_ServerMenu.onKeyGreen()); a
	# future backend with an analogous "linked account" concept can
	# implement them meaningfully instead of being stuck with a name that
	# says "Plex". Jellyfin's local PIN profiles are a different enough
	# model (see AbstractServerSettings.USER_SWITCH_LOCAL_PROFILES) that its
	# implementation of these four is just an inert stub.
	@abstractmethod
	def getSharedServerForUser(self):
		pass

	@abstractmethod
	def getAlternateUsers(self):
		pass

	@abstractmethod
	def switchUser(self, userId, pin):
		pass

	@abstractmethod
	def getUserTokenForLocalServerAuthentication(self, ipInConfig):
		pass

	@abstractmethod
	def getContextSubtitleStreams(self, context):
		"""Subtitle streams already embedded in a listing entry's context
		menu data (see DP_View.displaySubtitleMenu()), so the menu can be
		built without a separate server round-trip. Returns None if this
		backend never embeds that data (the caller falls back to
		getSubtitlesById() instead) or `context` does not carry any -
		never confuse "no streams" (an empty list) with "not supported"
		(None)."""
		pass

	@abstractmethod
	def getContextAudioStreams(self, context):
		"""Same idea as getContextSubtitleStreams(), for audio tracks (see
		DP_View.displayAudioMenu())."""
		pass

	@abstractmethod
	def getRemoteClientIdentifierHeaderNames(self):
		"""Ordered list of HTTP header names DPH_RemoteHandler.
		getClientIdentifier() should check, first match wins - each backend's
		own remote-control wire protocol names its client-identifier header
		differently (Plex: X-Plex-Client-Identifier; Jellyfin: X-Emby-Token/
		X-MediaBrowser-Token)."""
		pass

	@abstractmethod
	def getRemotePollHeaders(self, commandID):
		"""Headers DPH_RemoteHandler.answerPoll() sends with its long-poll
		response body (Content-Type + the matching Access-Control-Expose-
		Headers) - the body format itself (XML vs JSON) is a property of the
		subscription manager, not of this call."""
		pass

	@abstractmethod
	def getRemoteResourceDescriptor(self, boxName):
		"""The player/device descriptor DPH_RemoteHandler.getResourceXml()
		returns to a remote-control app probing this box - Plex expects XML,
		Jellyfin expects JSON, and the two describe different fields
		entirely, so this returns the whole finished body, not just a
		format flag."""
		pass

	@abstractmethod
	def getRemoteContentType(self):
		"""The Content-Type DPH_RemoteHandler.setXmlHeader() sends with
		every response body (Plex: text/xml; Jellyfin: application/json)."""
		pass

	@abstractmethod
	def getRemoteAccessControlHeaders(self) -> dict[str, str]:
		"""CORS/identification headers DPH_RemoteHandler.
		setAccessControlHeaders() sends on every response, including the
		Access-Control-Allow-Headers allowlist naming this backend's own
		client-identifier headers."""
		pass

	@abstractmethod
	def getContentUrl(self, address, path):
		pass

	@abstractmethod
	def getAuthDetails(self, details, url_format=True, prefix="&"):
		pass

	@abstractmethod
	def getNewMyPlexToken(self):
		pass

	@abstractmethod
	def getLastResponse(self):
		pass

	@abstractmethod
	def doRequest(self, url, myType="GET"):
		pass

	@abstractmethod
	def refreshLibrarySection(self, token):
		"""Ask the server to rescan the library section currently being
		browsed (DP_View's yellow "refresh Library" button at color level
		2) - `token` is opaque and backend-specific: Plex's own
		context['libraryRefreshURL'] is already the full URL to GET
		(unchanged, see DP_PlexLibrary.buildContextMenu()); Jellyfin's is
		the section's item id, POSTed to its /Items/{id}/Refresh endpoint.
		No-ops if `token` is falsy - not every listing (e.g. hero/similar
		suggestions, which never set this context field at all) has one."""
		pass

	@abstractmethod
	def mediaType(self, partData, server):
		pass


	@abstractmethod
	def checkFileLocation(self, remotePathPart, localPathPart):
		pass

	@abstractmethod
	def getStreamDataById(self, server, myId, loadExtraData=False):
		pass

	@abstractmethod
	def getSelectedSubtitleDataById(self, server, myId, forcedOnly=False):        pass

	@abstractmethod
	def getSubtitlesById(self, server, myId):
		pass

	@abstractmethod
	def getAudioById(self, server, myId):
		pass

	@abstractmethod
	def setSubtitleById(self, server, sub_id, part_id):
		pass

	@abstractmethod
	def setAudioById(self, server, audio_id, part_id):
		pass

	@abstractmethod
	def getExtraData(self, server, myId, myType, loadExtraData):
		pass

	@abstractmethod
	def getAudioSubtitlesMedia(self, server, myId, myType, loadExtraData):
		pass


	@abstractmethod
	def getSelectedEmbeddedSubtitleData(self):
		pass


	@abstractmethod
	def getMediaOptionsToPlay(self, myId, vids, override=False, myType="Video", loadExtraData=False):
		pass

	@abstractmethod
	def playLibraryMedia(self, myId, url, isExtraData=False):
		pass

	@abstractmethod
	def setAudioSubtitles(self, stream):
		pass

	@abstractmethod
	def getXmlTreeFromPlex(self, url, requestType="GET"):
		pass

	@abstractmethod
	def getXmlTreeFromUrl(self, url):
		pass

	@abstractmethod
	def getFakeXml(self):
		pass

	@abstractmethod
	def sessionID(self):
		pass


	@abstractmethod
	def getLastErrorMessage(self):
		pass

	@abstractmethod
	def getListFromTag(self, entry, tagName):
		pass

	@abstractmethod
	def getImage(self, data, server, myType, transcode=True):
		pass

	@abstractmethod
	def photoTranscode(self, server, url, width=999, height=999):
		pass

	@abstractmethod
	def watched(self, url):
		pass

	@abstractmethod
	def deleteMedia(self, url):
		pass

	@abstractmethod
	def buildContextMenu(self, url, ratingKey, server):
		pass


	@abstractmethod
	def getUrlPathFormURL(self, url):
		pass

	@abstractmethod
	def getServerFromURL(self, url) -> str:
		pass

	@abstractmethod
	def getLinkURL(self, url, pathData, server):
		pass


	@abstractmethod
	def getTranscodeSettings(self, override=False):
		pass

	@abstractmethod
	def get_hTokenForServer(self, server) -> dict[str, str]:
		pass

	@abstractmethod
	def get_aTokenForServer(self, server):
		pass

	@abstractmethod
	def get_uTokenForServer(self, server):
		pass

	@abstractmethod
	def getServerName(self):
		pass

	@abstractmethod
	def setServerDetails(self):
		pass

	@abstractmethod
	def getUniversalTranscoderSettings(self):
		pass

	@abstractmethod
	def transcode(self, myID, url):
		pass


	@abstractmethod
	def getFullListEntry(self, entryData, url, viewState=None, isDirectory=False):
		pass

	@abstractmethod
	def getViewStateForShowEntry(self, entryData):
		pass

	@abstractmethod
	def getViewStatefromViewCount(self, entryData):
		pass

	@abstractmethod
	def getServerConfig(self):
		pass

