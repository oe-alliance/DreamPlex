# -*- coding: utf-8 -*-
"""Robustness tests: manual access token precedence, HTTP redirect
following, container pagination and modern-PMS attribute guards."""

import threading
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()


class RobustnessTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)

	def newPlex(self, **kwargs):
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def url(self, path):
		return "http://%s%s" % (self.mock.address, path)


class TestRedirects(RobustnessTestCase):
	def setUp(self):
		RobustnessTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def test_absolute_redirect_is_followed(self):
		self.mock.add_redirect("/old/sections", self.url("/library/sections"), status=302)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/old/sections"))
		self.assertTrue(body)
		self.assertIn(b"MediaContainer", body)
		self.assertEqual([r["path"] for r in self.mock.requests],
						["/old/sections", "/library/sections"])

	def test_relative_redirect_is_followed(self):
		self.mock.add_redirect("/old/relative", "/library/sections", status=301)
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrl(self.url("/old/relative"))
		self.assertEqual(tree.tag, "MediaContainer")
		self.assertEqual(len(tree.findall("Directory")), 3)

	def test_redirect_chain_up_to_three_hops(self):
		self.mock.add_redirect("/hop1", "/hop2", status=302)
		self.mock.add_redirect("/hop2", "/hop3", status=307)
		self.mock.add_redirect("/hop3", "/library/sections", status=308)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/hop1"))
		self.assertTrue(body)
		self.assertIn(b"MediaContainer", body)

	def test_redirect_loop_gives_up(self):
		self.mock.add_redirect("/loop", "/loop", status=302)
		plex = self.newPlex()

		result = plex.doRequest(self.url("/loop"))
		self.assertFalse(result)
		self.assertIn("redirect", plex.lastError.lower())

	def test_303_switches_to_get(self):
		self.mock.add_redirect("/see/other", "/library/sections", status=303)
		plex = self.newPlex()

		body = plex.doRequest(self.url("/see/other"), myType="PUT")
		self.assertTrue(body)
		methods = [(r["method"], r["path"]) for r in self.mock.requests]
		self.assertEqual(methods, [("PUT", "/see/other"), ("GET", "/library/sections")])


class TestPagination(RobustnessTestCase):
	def pagedItems(self, count):
		return ['<Video ratingKey="%d" key="/library/metadata/%d" type="movie" title="Movie %d"/>'
				% (i, i, i) for i in range(count)]

	def test_pages_are_merged(self):
		self.mock.add_paged("/library/sections/1/all", self.pagedItems(5),
						attrs={"title2": "All Movies"})
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrlPaged(self.url("/library/sections/1/all"), pageSize=2)

		videos = tree.findall("Video")
		self.assertEqual([v.get("title") for v in videos],
						["Movie 0", "Movie 1", "Movie 2", "Movie 3", "Movie 4"])
		self.assertEqual(tree.get("size"), "5")

		starts = [r["headers"].get("x-plex-container-start")
				for r in self.mock.requests_for("/library/sections/1/all")]
		self.assertEqual(starts, ["0", "2", "4"])

	def test_unpaged_server_needs_single_request(self):
		# a plain xml route has no totalSize -> the merger must stop after one page
		self.mock.add_xml("/library/sections/1/all", helpers.fixture("movies_all.xml"))
		plex = self.newPlex()

		tree = plex.getXmlTreeFromUrlPaged(self.url("/library/sections/1/all"))

		self.assertEqual(len(tree.findall("Video")), 2)
		self.assertEqual(len(self.mock.requests_for("/library/sections/1/all")), 1)

	def test_media_parser_reads_all_pages(self):
		self.mock.add_paged("/library/sections/1/all", self.pagedItems(450),
						attrs={"title2": "All Movies"})
		plex = self.newPlex()

		fullList, mediaContainer = plex.getMoviesFromSection(self.url("/library/sections/1/all"))

		self.assertEqual(len(fullList), 450)
		self.assertEqual(len(self.mock.requests_for("/library/sections/1/all")), 3)  # 200+200+50
		self.assertEqual(mediaContainer["title2"], "All Movies")


class TestManualAccessToken(RobustnessTestCase):
	def setUp(self):
		RobustnessTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def lastTokenHeader(self):
		return self.mock.requests_for("/library/sections")[-1]["headers"].get("x-plex-token")

	def test_manual_token_wins_over_local_auth(self):
		plex = self.newPlex(accessToken="MANUAL-TOKEN", localAuth=True,
						myplexToken="PLEXTV-TOKEN", myplexLocalToken="LOCAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "MANUAL-TOKEN")
		self.assertEqual(plex.get_rawTokenForServer(self.mock.address), "MANUAL-TOKEN")

	def test_manual_token_works_without_local_auth(self):
		plex = self.newPlex(accessToken="MANUAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "MANUAL-TOKEN")

	def test_local_auth_still_works_without_manual_token(self):
		plex = self.newPlex(localAuth=True, myplexToken="PLEXTV-TOKEN",
						myplexLocalToken="LOCAL-TOKEN")
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "LOCAL-TOKEN")

	def test_old_saved_config_without_token_field(self):
		# configs saved by older plugin versions have no accessToken element
		helpers.get_config()  # ensure the package is imported
		serverConfig = helpers.make_server_config(
			host=self.mock.host, port=self.mock.port,
			localAuth=True, myplexToken="PLEXTV-TOKEN", myplexLocalToken="LOCAL-TOKEN")
		delattr(serverConfig, "accessToken")

		from src.DP_PlexLibrary import PlexLibrary
		plex = PlexLibrary(session=None, serverConfig=serverConfig)
		plex.doRequest(self.url("/library/sections"))

		self.assertEqual(self.lastTokenHeader(), "LOCAL-TOKEN")


class TestMultiVersionMedia(RobustnessTestCase):
	"""An item with several <Media> children (versions) must expose the
	parts of ALL of them, labelled with resolution/codec."""

	def setUp(self):
		RobustnessTestCase.setUp(self)
		self.mock.add_xml("/library/metadata/1002", helpers.fixture("metadata_multiversion.xml"))

	def test_all_versions_are_offered(self):
		plex = self.newPlex()
		count, options, server = plex.getMediaOptionsToPlay(
			"1002", self.url("/library/sections/1/all"), False, myType="Video")

		self.assertEqual(count, 2)
		self.assertTrue(options[0][0].endswith("file-1080.mkv"))
		self.assertTrue(options[1][0].endswith("file-4k.mkv"))
		# version label fields
		self.assertEqual((options[0][5], options[0][6]), ("1080", "h264"))
		self.assertEqual((options[1][5], options[1][6]), ("4k", "hevc"))

	def test_options_carry_the_media_index(self):
		plex = self.newPlex()
		count, options, server = plex.getMediaOptionsToPlay(
			"1002", self.url("/library/sections/1/all"), False, myType="Video")

		self.assertEqual(options[0][7], 0)
		self.assertEqual(options[1][7], 1)

	def test_transcoder_receives_the_chosen_version(self):
		self.mock.add_xml("/", helpers.fixture("server_root.xml"))
		self.mock.add_raw("/video/:/transcode/universal/start.m3u8",
						"application/vnd.apple.mpegurl", helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", localAuth=True,
						myplexToken="PT", myplexLocalToken="LT")
		count, options, server = plex.getMediaOptionsToPlay(
			"1002", self.url("/library/sections/1/all"), False, myType="Video")

		plex.setSelectedVersion(options[1][7])  # what DP_Player does on choice
		url = plex.mediaType({"key": options[1][0], "file": options[1][1]}, server)
		plex.playLibraryMedia("1002", url)

		query = self.mock.requests_for("/video/:/transcode/universal/start.m3u8")[-1]["query"]
		self.assertEqual(query.get("mediaIndex"), ["1"])
		self.assertEqual(query.get("partIndex"), ["0"])

	def test_transcoder_omits_media_index_without_selection(self):
		self.mock.add_xml("/", helpers.fixture("server_root.xml"))
		self.mock.add_xml("/library/metadata/1001", helpers.fixture("metadata_video.xml"))
		self.mock.add_raw("/video/:/transcode/universal/start.m3u8",
						"application/vnd.apple.mpegurl", helpers.fixture("start.m3u8"))
		plex = self.newPlex(playbackType="1", localAuth=True,
						myplexToken="PT", myplexLocalToken="LT")
		count, options, server = plex.getMediaOptionsToPlay(
			"1001", self.url("/library/sections/1/all"), False, myType="Video")
		url = plex.mediaType({"key": options[0][0], "file": options[0][1]}, server)
		plex.playLibraryMedia("1001", url)

		query = self.mock.requests_for("/video/:/transcode/universal/start.m3u8")[-1]["query"]
		self.assertNotIn("mediaIndex", query)

	def test_stream_preselection_still_uses_first_version(self):
		plex = self.newPlex()
		plex.getMediaOptionsToPlay("1002", self.url("/library/sections/1/all"), False, myType="Video")

		# audio preselection parsed only from the first <Media>, as before
		self.assertEqual(plex.streams["audioCount"], 1)
		self.assertEqual(plex.streams["audio"].get("codec"), "ac3")


class TestTrailerExtras(RobustnessTestCase):
	"""loadExtraData=True must expose playable trailers, both from the
	Extras subtree and from the modern primaryExtraKey reference."""

	def test_extras_subtree_is_listed(self):
		self.mock.add_xml("/library/metadata/1003", helpers.fixture("metadata_trailer_extras.xml"))
		plex = self.newPlex()
		count, options, server = plex.getMediaOptionsToPlay(
			"1003", self.url("/library/sections/1/all"), False, myType="Video", loadExtraData=True)

		self.assertEqual(count, 1)
		self.assertTrue(options[0][0].endswith("delta-trailer.mp4"))
		self.assertTrue(options[0][1].startswith("clip: Delta Movie Trailer"))
		self.assertEqual(options[0][5], "9001")

	def test_primary_extra_key_fallback(self):
		self.mock.add_xml("/library/metadata/1004", helpers.fixture("metadata_primary_extra.xml"))
		self.mock.add_xml("/library/metadata/9002", helpers.fixture("metadata_trailer_clip.xml"))
		plex = self.newPlex()
		count, options, server = plex.getMediaOptionsToPlay(
			"1004", self.url("/library/sections/1/all"), False, myType="Video", loadExtraData=True)

		self.assertEqual(count, 1)
		self.assertTrue(options[0][0].endswith("epsilon-trailer.mp4"))
		self.assertEqual(options[0][5], "9002")
		# the fallback resolved the extra through its own metadata
		self.assertEqual(len(self.mock.requests_for("/library/metadata/9002")), 1)

	def test_no_extras_at_all_yields_empty(self):
		self.mock.add_xml("/library/metadata/1001", helpers.fixture("metadata_video.xml"))
		plex = self.newPlex()
		count, options, server = plex.getMediaOptionsToPlay(
			"1001", self.url("/library/sections/1/all"), False, myType="Video", loadExtraData=True)

		self.assertEqual(count, 0)
		self.assertEqual(options, [])


class QueueingReactor(object):
	"""Stands in for the twisted reactor: keeps what the worker hands over
	instead of running it, so the test decides when - and on which thread -
	the callback runs, as the real main loop would."""

	def __init__(self):
		self.handedOver = threading.Event()
		self.pending = []

	def callFromThread(self, fn, *args, **kwargs):
		self.pending.append((fn, args, kwargs))
		self.handedOver.set()

	def runPending(self):
		for fn, args, kwargs in self.pending:
			fn(*args, **kwargs)


class TestRunInThread(unittest.TestCase):
	"""Network I/O must be delivered back through a callback so it can run
	off the enigma2 main loop (a long block there kills enigma2).

	runInThread() has two branches and every test here pins the one it means.
	These tests used to run whichever branch sys.path happened to select: they
	were written against the synchronous one, and when tests/stubs gained a
	twisted stub for an unrelated fix they silently moved to the threaded one -
	where they read the result without waiting for the worker, and failed now
	and then on Python 2 (about 3 calls in 1,000).

	Once the queue has run, the threaded tests also join the worker and want
	exactly one delivery, on their own thread. Checking only that onDone had
	not run before the hand-over let a worker through that handed over and
	THEN ran onDone itself, off the main loop: caught only when the worker
	happened to be quick, and never with a pause between the two. The join is
	skipped when the work ran on the test's own thread: joining the current
	thread raises, and would fail all three threaded tests with that instead
	of just the one that exists to report it. Found and measured by the
	DreamFin fork."""

	def setUp(self):
		import src.__common__ as common
		self.common = common
		self.addCleanup(setattr, common, "reactor", common.reactor)

	def runThreaded(self, work):
		"""Run work through the threaded branch; return what was seen."""
		reactor = QueueingReactor()
		self.common.reactor = reactor
		seen = {"onDoneThreads": []}

		def recordingWork():
			seen["workThread"] = threading.current_thread()
			return work()

		def onDone(result, error):
			seen["onDoneThreads"].append(threading.current_thread())
			seen["result"], seen["error"] = result, error

		self.common.runInThread(recordingWork, onDone)  # must not raise

		# wait for the hand-over itself, never for a fixed time
		self.assertTrue(reactor.handedOver.wait(10),
				"the worker never handed its result to the reactor")
		self.assertNotIn("result", seen,
				"onDone ran on the worker thread instead of going through the reactor")
		reactor.runPending()

		# the worker must be done, and must not have delivered a second time
		worker = seen["workThread"]
		if worker is not threading.current_thread():  # else: its own test says so
			worker.join(10)
			self.assertFalse(worker.is_alive(), "the worker thread never finished")
		self.assertEqual(seen["onDoneThreads"], [threading.current_thread()],
				"onDone must run exactly once, and on the main loop's thread")

		return seen

	def test_the_work_runs_off_the_callers_thread(self):
		seen = self.runThreaded(lambda: 21 * 2)

		self.assertIsNot(seen["workThread"], threading.current_thread(),
				"the work ran on the caller's thread, so runInThread blocked it")

	def test_result_is_delivered_through_the_reactor(self):
		seen = self.runThreaded(lambda: 21 * 2)

		self.assertEqual(seen["result"], 42)
		self.assertIsNone(seen["error"])

	def test_exception_is_delivered_not_raised(self):
		def work():
			raise IOError("boom")

		seen = self.runThreaded(work)

		self.assertIsNone(seen["result"])
		self.assertIsInstance(seen["error"], IOError)

	def test_without_a_reactor_the_result_is_delivered_before_returning(self):
		self.common.reactor = None
		seen = {}

		def onDone(result, error):
			seen["result"], seen["error"] = result, error

		self.common.runInThread(lambda: 21 * 2, onDone)

		# no waiting on purpose: this branch is synchronous by design
		self.assertEqual(seen["result"], 42)
		self.assertIsNone(seen["error"])

	def test_without_a_reactor_an_exception_is_delivered_not_raised(self):
		self.common.reactor = None
		seen = {}

		def work():
			raise IOError("boom")

		def onDone(result, error):
			seen["result"], seen["error"] = result, error

		self.common.runInThread(work, onDone)  # must not raise

		self.assertIsNone(seen["result"])
		self.assertIsInstance(seen["error"], IOError)


class TestMediaChoiceName(unittest.TestCase):
	"""The "Select media to play" labels must be native str: on py2 the
	enigma2 listbox renders a unicode label as "<not a string>", which is
	exactly what non-ascii file names produced (py2 etree hands non-ascii
	attribute values over as unicode)."""

	def test_non_ascii_file_name_yields_native_str(self):
		from src.__common__ import buildMediaChoiceName
		items = (u"/library/parts/1/file.mkv",
				u"/data/Pel·lis/La película (2024)/La película 4K.mkv",
				u"mkv", u"2600000000", u"7200", u"4k", u"hevc", 0)

		name = buildMediaChoiceName(items)

		self.assertIsInstance(name, str)  # native str on BOTH pythons
		expected = u"[4k / hevc / 2.42 GB]  La película 4K.mkv"
		if str is bytes:  # py2: utf-8 encoded bytes
			self.assertEqual(name, expected.encode("utf-8"))
		else:
			self.assertEqual(name, expected)

	def test_version_prefix_and_basename(self):
		from src.__common__ import buildMediaChoiceName
		items = ("/library/parts/2/file.mkv", "/data/movies/Movie.1080p.mkv",
				"mkv", "1073741824", "5400", "1080", "h264", 1)

		self.assertEqual(buildMediaChoiceName(items),
				"[1080 / h264 / 1.0 GB]  Movie.1080p.mkv")

	def test_no_file_name_falls_back_to_key_and_stays_str(self):
		from src.__common__ import buildMediaChoiceName
		items = (u"película", None, u"mkv", u"1048576", u"61")

		name = buildMediaChoiceName(items)

		self.assertIsInstance(name, str)
		expected = u"película (mkv / 1.0 MB / 00:01:01)"
		if str is bytes:
			self.assertEqual(name, expected.encode("utf-8"))
		else:
			self.assertEqual(name, expected)


class TestRatingValue(unittest.TestCase):
	"""The rating stars must reflect the score modern Plex actually sends:
	current PMS reports "audienceRating" and only rarely a critic "rating"."""

	def test_audience_rating_used_when_no_critic_rating(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"audienceRating": "5.5"}), 5.5)

	def test_critic_rating_is_preferred(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"rating": "7.8", "audienceRating": "5.5"}), 7.8)

	def test_falls_back_past_zero_critic_rating(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"rating": "0.0", "audienceRating": "6.4"}), 6.4)

	def test_user_rating_is_last_resort(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"userRating": "9"}), 9.0)

	def test_no_score_returns_zero(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"title": "x"}), 0.0)

	def test_garbage_value_is_skipped(self):
		from src.__common__ import getRatingValue
		self.assertEqual(getRatingValue({"rating": "N/A", "audienceRating": "7.2"}), 7.2)


class TestPlexTvUnreachable(RobustnessTestCase):
	"""A plex.tv HTTPS failure (old box OpenSSL, network down) must not
	crash the plugin - it should report the error and return False."""

	def test_getXmlTreeFromPlex_survives_connection_failure(self):
		plex = self.newPlex()
		# point plex.tv at a closed port so the HTTPS connect fails fast
		import src.DP_PlexLibrary as lib
		original = lib.PLEXTV_SERVER
		lib.PLEXTV_SERVER = "127.0.0.1"
		self.addCleanup(setattr, lib, "PLEXTV_SERVER", original)
		plex.serverConfig_myplexToken = "x"

		result = plex.getXmlTreeFromPlex("/pms/system/library/sections")

		self.assertFalse(result)
		self.assertTrue(plex.lastError)
		self.assertIn("plex.tv", plex.lastError)


class TestModernContainerGuards(RobustnessTestCase):
	def test_shows_without_title2_do_not_crash(self):
		self.mock.add_xml("/library/sections/2/recentlyAdded",
						helpers.fixture("shows_no_title2.xml"))
		plex = self.newPlex()

		fullList, mediaContainer = plex.getShowsFromSection(
			self.url("/library/sections/2/recentlyAdded"))

		self.assertEqual(len(fullList), 1)
		self.assertEqual(fullList[0][0], "Alpha Show")
		self.assertNotIn("title2", mediaContainer)


if __name__ == "__main__":
	unittest.main()
