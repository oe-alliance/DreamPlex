# -*- coding: utf-8 -*-
"""Bug 2 regression tests: the transcode URL builder must work on
Python 3 (bytes-safe m3u8 parsing), drop the 2010 X-Plex-Access
signature, carry the X-Plex-Token in playback URLs and never crash on
a missing token."""

import re
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()


def withoutSession(url):
	"""Drop the per-playback session id, which is random by design."""
	return re.sub(r"[?&]X-Plex-Session-Identifier=[^&]*", "", url)


class PlaybackTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.mock.add_xml("/", helpers.fixture("server_root.xml"))
		self.mock.add_xml("/library/metadata/1001", helpers.fixture("metadata_video.xml"))

	def newPlex(self, **kwargs):
		kwargs.setdefault("localAuth", True)
		kwargs.setdefault("myplexToken", "PLEXTV-TOKEN")
		kwargs.setdefault("myplexLocalToken", "LOCAL-TOKEN")
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def playFirstPart(self, plex):
		"""Mimic DP_Player: options -> mediaType -> playLibraryMedia."""
		vids = "http://%s/library/sections/1/all" % self.mock.address
		count, options, server = plex.getMediaOptionsToPlay("1001", vids, False, myType="Video")
		self.assertEqual(count, 1)
		mediaFileUrl = plex.mediaType({"key": options[0][0], "file": options[0][1]}, server)
		return plex.playLibraryMedia("1001", mediaFileUrl)


class TestAppendTokenToUrl(PlaybackTestCase):
	def test_token_is_appended_with_correct_separator(self):
		plex = self.newPlex()
		server = self.mock.address
		base = "http://%s/library/parts/3001/file.mkv" % server

		self.assertEqual(plex.appendTokenToUrl(base, server),
						base + "?X-Plex-Token=LOCAL-TOKEN")
		self.assertEqual(plex.appendTokenToUrl(base + "?a=1", server),
						base + "?a=1&X-Plex-Token=LOCAL-TOKEN")

	def test_append_is_idempotent(self):
		plex = self.newPlex()
		server = self.mock.address
		url = "http://%s/video?X-Plex-Token=LOCAL-TOKEN" % server
		self.assertEqual(plex.appendTokenToUrl(url, server), url)

	def test_without_token_url_is_unchanged(self):
		plex = self.newPlex(localAuth=False, myplexToken="", myplexLocalToken="")
		url = "http://%s/library/parts/3001/file.mkv" % self.mock.address
		self.assertEqual(plex.appendTokenToUrl(url, self.mock.address), url)

	def test_unknown_server_returns_url_unchanged(self):
		plex = self.newPlex()
		url = "http://192.0.2.1:32400/library/parts/1/file.mkv"
		self.assertEqual(plex.appendTokenToUrl(url, "192.0.2.1:32400"), url)


class TestStreamedPlayback(PlaybackTestCase):
	def test_raw_stream_url_carries_token(self):
		plex = self.newPlex(playbackType="0")
		playerData = self.playFirstPart(plex)

		self.assertEqual(withoutSession(playerData["playUrl"]),
						"http://%s/library/parts/3001/1700000000/file.mkv?X-Plex-Token=LOCAL-TOKEN"
						% self.mock.address)
		self.assertEqual(playerData["resumeStamp"], 60000)

	def test_raw_stream_without_token_does_not_crash(self):
		plex = self.newPlex(playbackType="0", localAuth=False,
						myplexToken="", myplexLocalToken="")
		playerData = self.playFirstPart(plex)

		# upstream crashed here with TypeError: url + None
		self.assertEqual(withoutSession(playerData["playUrl"]),
						"http://%s/library/parts/3001/1700000000/file.mkv" % self.mock.address)


class TestUniversalTranscoder(PlaybackTestCase):
	M3U8_PATH = "/video/:/transcode/universal/start.m3u8"

	def test_transcode_url_is_py3_safe_and_tokenized(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertEqual(withoutSession(playUrl),
						"http://%s/video/:/transcode/universal/"
						"session/f00dcafe-0000-1111-2222-333344445555/base/index.m3u8"
						"?X-Plex-Token=LOCAL-TOKEN" % self.mock.address)
		self.assertNotIn("b'", playUrl)  # the py3 bytes corruption

	def test_prefetch_request_is_authenticated_and_unsigned(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		self.playFirstPart(plex)

		prefetch = self.mock.requests_for(self.M3U8_PATH)[-1]
		headers = prefetch["headers"]
		self.assertEqual(headers.get("x-plex-token"), "LOCAL-TOKEN")
		self.assertEqual(headers.get("x-plex-product"), "DreamPlex")

		# the 2010 signature scheme must be gone
		self.assertNotIn("x-plex-access-code", headers)
		self.assertNotIn("x-plex-access-key", headers)
		self.assertNotIn("x-plex-access-time", headers)

		query = prefetch["query"]
		# the transcode runs under the playback session, not under the
		# client uuid: the server has to see stream and reports as one
		self.assertEqual(query.get("session"), [plex.g_playSessionID])
		self.assertEqual(query.get("protocol"), ["hls"])
		self.assertEqual(query.get("X-Plex-Token"), ["LOCAL-TOKEN"])
		# the universal transcoder needs the library path of the item
		self.assertEqual(query.get("path"),
						["http://127.0.0.1:32400/library/metadata/1001"])

	def test_h264_is_the_default_and_asks_for_no_profile(self):
		# leaving the server's own profile alone is what keeps h264 working
		# on every server and decoder
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")

		self.assertIsNone(plex.getTranscodeProfileExtra())

		self.playFirstPart(plex)
		headers = self.mock.requests_for(self.M3U8_PATH)[-1]["headers"]
		self.assertNotIn("x-plex-client-profile-extra", headers)

	def test_hevc_option_asks_the_server_for_hevc(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", transcodeVideoCodec="hevc")
		self.playFirstPart(plex)

		headers = self.mock.requests_for(self.M3U8_PATH)[-1]["headers"]
		profile = headers.get("x-plex-client-profile-extra")
		self.assertTrue(profile, "the HEVC directive must travel with the request")
		self.assertIn("videoCodec=hevc", profile)
		# without protocol= the PMS drops the directive and silently encodes
		# h264, so this is the part that actually makes it work
		self.assertIn("protocol=hls", profile)
		self.assertIn("type=videoProfile", profile)
		self.assertEqual(headers.get("x-plex-client-profile-name"), "generic")

	def test_h264_ladder_is_untouched(self):
		plex = self.newPlex(playbackType="1", uniQuality="4")

		self.assertEqual(plex.getUniversalTranscoderSettings(),
						("75", "1280x720", "3000"))

	def test_hevc_uses_its_own_ladder(self):
		# same bitrate as h264 step 4, but 1080p instead of 720p
		plex = self.newPlex(playbackType="1", transcodeVideoCodec="hevc",
						uniQuality="4", uniQualityHevc="4")

		self.assertEqual(plex.getUniversalTranscoderSettings(),
						("75", "1920x1080", "3000"))

	def test_hevc_ladder_reaches_beyond_1080p(self):
		# the top step is 1440p: a 1.43 server delivered it for real, but
		# refused 2160p and silently sent 1080p instead
		plex = self.newPlex(playbackType="1", transcodeVideoCodec="hevc",
						uniQualityHevc="6")

		videoQuality, videoResolution, maxVideoBitrate = plex.getUniversalTranscoderSettings()
		self.assertEqual(videoResolution, "2560x1440")
		self.assertEqual(maxVideoBitrate, "8000")

	def test_hevc_ladder_travels_in_the_session_url(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", transcodeVideoCodec="hevc",
						uniQualityHevc="6")
		self.playFirstPart(plex)

		query = self.mock.requests_for(self.M3U8_PATH)[-1]["query"]
		self.assertEqual(query.get("videoResolution"), ["2560x1440"])
		self.assertEqual(query.get("maxVideoBitrate"), ["8000"])

	def test_fallback_to_master_playlist_when_no_media_urls(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start_comments_only.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertTrue(playUrl.startswith(
			"http://%s/video/:/transcode/universal/start.m3u8?" % self.mock.address))
		self.assertIn("session=%s" % plex.g_playSessionID, playUrl)
		self.assertIn("&X-Plex-Token=LOCAL-TOKEN", playUrl)

	def test_fallback_when_server_answers_error(self):
		self.mock.add_error(self.M3U8_PATH, 500)
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertTrue(playUrl.startswith(
			"http://%s/video/:/transcode/universal/start.m3u8?" % self.mock.address))
		self.assertIn("&X-Plex-Token=LOCAL-TOKEN", playUrl)


class TestPlaybackSession(PlaybackTestCase):
	"""X-Plex-Session-Identifier: what the "now playing" dashboard needs.

	Upstream never sent one, so the server could not tie the stream to the
	timeline reports and the box stayed invisible while playing.
	"""

	M3U8_PATH = "/video/:/transcode/universal/start.m3u8"

	def test_stream_url_carries_a_session(self):
		plex = self.newPlex(playbackType="0")
		playerData = self.playFirstPart(plex)

		session = playerData["playSessionID"]
		self.assertTrue(session)
		self.assertIn("X-Plex-Session-Identifier=" + session, playerData["playUrl"])

	def test_each_playback_gets_its_own_session(self):
		plex = self.newPlex(playbackType="0")

		first = self.playFirstPart(plex)["playSessionID"]
		second = self.playFirstPart(plex)["playSessionID"]

		self.assertNotEqual(first, second)

	def test_transcode_request_is_filed_under_the_session(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)

		headers = self.mock.requests_for(self.M3U8_PATH)[-1]["headers"]
		self.assertEqual(headers.get("x-plex-session-identifier"),
						playerData["playSessionID"])

	def test_transcode_and_reports_share_one_identity(self):
		# the whole point: the server has to be able to match the stream it
		# is transcoding with the progress reports coming in
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1")
		playerData = self.playFirstPart(plex)

		query = self.mock.requests_for(self.M3U8_PATH)[-1]["query"]
		self.assertEqual(query.get("session"), [playerData["playSessionID"]])
		self.assertEqual(playerData["transcodingSession"], playerData["playSessionID"])

	def test_session_is_appended_only_once(self):
		plex = self.newPlex(playbackType="0")
		url = "http://%s/library/parts/1/file.mkv" % self.mock.address

		once = plex.appendSessionToUrl(url)
		self.assertEqual(plex.appendSessionToUrl(once), once)


class TestSegmentedTranscoder(PlaybackTestCase):
	M3U8_PATH = "/video/:/transcode/segmented/start.m3u8"

	def test_segmented_branch_is_py3_safe(self):
		self.mock.add_raw(self.M3U8_PATH, "application/vnd.apple.mpegurl",
						helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", universalTranscoder=False)
		playerData = self.playFirstPart(plex)
		playUrl = playerData["playUrl"]

		self.assertEqual(withoutSession(playUrl),
						"http://%s/video/:/transcode/segmented/"
						"session/f00dcafe-0000-1111-2222-333344445555/base/index.m3u8"
						"?X-Plex-Token=LOCAL-TOKEN" % self.mock.address)
		self.assertNotIn("b'", playUrl)

		prefetch = self.mock.requests_for(self.M3U8_PATH)[-1]
		self.assertEqual(prefetch["query"].get("ratingKey"), ["1001"])
		self.assertNotIn("x-plex-access-code", prefetch["headers"])


if __name__ == "__main__":
	unittest.main()
