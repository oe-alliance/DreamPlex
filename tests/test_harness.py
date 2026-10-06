# -*- coding: utf-8 -*-
"""Baseline tests: prove the offline harness can drive the unmodified
plugin code (import, instantiation, section listing, legacy filter menu,
request headers) against a mock Plex Media Server."""

import unittest

try:
	from urllib.request import urlopen, Request
except ImportError:  # Python 2
	from urllib2 import urlopen, Request

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

from src.__plugin__ import Plugin  # noqa: E402


class MockedPMSTestCase(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)

	def newPlex(self, **kwargs):
		return helpers.make_plex_instance(mock=self.mock, **kwargs)

	def findEntry(self, fullList, title):
		for entry in fullList:
			if entry[0] == title:
				return entry
		self.fail("entry %r not found in %r" % (title, [e[0] for e in fullList]))


class TestInstantiation(MockedPMSTestCase):
	def test_instance_targets_mock_server(self):
		plex = self.newPlex()
		self.assertEqual(plex.g_currentServer, self.mock.address)
		self.assertEqual(plex.g_serverDict["address"], self.mock.address)
		self.assertEqual(plex.g_serverDict["discovery"], "local")

	def test_server_details_are_parsed(self):
		self.mock.add_xml("/", helpers.fixture("server_root.xml"))
		plex = self.newPlex()
		plex.setServerDetails()
		self.assertEqual(plex.g_serverVersion, "1.40.0.7998")
		self.assertTrue(plex.g_multiUser)


class TestGetAllSections(MockedPMSTestCase):
	def setUp(self):
		MockedPMSTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def test_sections_with_filter_menu(self):
		plex = self.newPlex(showFilter=True)
		fullList = plex.getAllSections()

		# 3 sections + On Deck + New inserted at the top
		self.assertEqual(len(fullList), 5)
		self.assertEqual(fullList[0][0], "On Deck")
		self.assertEqual(fullList[1][0], "New")

		movies = self.findEntry(fullList, "Movies")
		self.assertEqual(movies[1], Plugin.MENU_FILTER)
		self.assertEqual(movies[2], "movieEntry")
		self.assertEqual(movies[3]["contentUrl"],
						"http://%s/library/sections/1" % self.mock.address)

		shows = self.findEntry(fullList, "TV Shows")
		self.assertEqual(shows[1], Plugin.MENU_FILTER)
		self.assertEqual(shows[2], "showEntry")

		music = self.findEntry(fullList, "Music")
		self.assertEqual(music[1], Plugin.MENU_FILTER)
		self.assertEqual(music[2], "musicEntry")

	def test_sections_without_filter_menu(self):
		plex = self.newPlex(showFilter=False)
		fullList = plex.getAllSections()

		movies = self.findEntry(fullList, "Movies")
		# no filter -> content url points directly at /all
		self.assertTrue(movies[3]["contentUrl"].endswith("/library/sections/1/all"))
		self.assertNotEqual(movies[1], Plugin.MENU_FILTER)

		# music does not support the no-filter mode, stays a filter entry
		music = self.findEntry(fullList, "Music")
		self.assertEqual(music[1], Plugin.MENU_FILTER)
		self.assertFalse(music[3]["contentUrl"].endswith("/all"))


class TestLegacySectionFilter(MockedPMSTestCase):
	"""Old PMS servers answer /library/sections/<id> with Directory
	children; that passthrough behaviour must keep working."""

	def setUp(self):
		MockedPMSTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))
		self.mock.add_xml("/library/sections/1", helpers.fixture("section_root_legacy.xml"))

	def test_server_provided_filter_menu_passthrough(self):
		plex = self.newPlex(showFilter=True)
		movies = self.findEntry(plex.getAllSections(), "Movies")

		menu = plex.getSectionFilter(movies[3])
		self.assertEqual(len(menu), 6)

		allEntry = self.findEntry(menu, "All Movies")
		self.assertEqual(allEntry[2], "movieEntry")
		self.assertTrue(allEntry[3]["contentUrl"].endswith("/library/sections/1/all"))

		genre = self.findEntry(menu, "By Genre")
		self.assertEqual(genre[1], Plugin.MENU_FILTER)
		self.assertEqual(genre[2], "showFilter")
		self.assertTrue(genre[3]["hasSecondaryTag"])
		self.assertTrue(genre[3]["contentUrl"].endswith("/library/sections/1/genre"))

		search = self.findEntry(menu, "Search...")
		self.assertTrue(search[3]["hasPromptTag"])
		self.assertTrue(search[3]["contentUrl"].endswith("/library/sections/1/search?type=1"))


class TestRequests(MockedPMSTestCase):
	def setUp(self):
		MockedPMSTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def test_plex_headers_and_local_token_are_sent(self):
		plex = self.newPlex(localAuth=True, myplexToken="PLEXTV-TOKEN",
						myplexLocalToken="LOCAL-TOKEN")
		plex.doRequest("http://%s/library/sections" % self.mock.address)

		request = self.mock.requests_for("/library/sections")[-1]
		self.assertEqual(request["headers"].get("x-plex-token"), "LOCAL-TOKEN")
		self.assertEqual(request["headers"].get("x-plex-product"), "DreamPlex")
		self.assertTrue(request["headers"].get("x-plex-client-identifier"))

	def test_http_error_sets_last_error(self):
		plex = self.newPlex()
		result = plex.doRequest("http://%s/does/not/exist" % self.mock.address)
		self.assertFalse(result)
		self.assertIn("404", plex.lastError)

	def test_invalid_xml_yields_fake_tree(self):
		self.mock.add_raw("/garbage", "text/plain", "this is } not { xml")
		plex = self.newPlex()
		tree = plex.getXmlTreeFromUrl("http://%s/garbage" % self.mock.address)
		self.assertEqual(tree.tag, "xml")
		self.assertEqual(len(tree.findall("Directory")), 0)


class TestMediaParsing(MockedPMSTestCase):
	def setUp(self):
		MockedPMSTestCase.setUp(self)
		self.mock.add_xml("/library/sections", helpers.fixture("sections.xml"))

	def test_movies_from_section(self):
		self.mock.add_xml("/library/sections/1/all", helpers.fixture("movies_all.xml"))
		plex = self.newPlex()
		fullList, mediaContainer = plex.getMoviesFromSection(
			"http://%s/library/sections/1/all" % self.mock.address)

		self.assertEqual(mediaContainer["title2"], "All Movies")
		self.assertEqual(len(fullList), 2)

		title, entryData, contextMenu, viewState, nextUrl = self.findEntry(fullList, "Alpha Movie")
		self.assertEqual(viewState, "unseen")
		self.assertEqual(entryData["mediaDataArr"][0]["Parts"][0]["id"], "3001")
		self.assertTrue(nextUrl.endswith("/library/metadata/1001"))

		betaState = self.findEntry(fullList, "Beta Movie")[3]
		self.assertEqual(betaState, "seen")

	def test_shows_from_section(self):
		self.mock.add_xml("/library/sections/2/all", helpers.fixture("shows_all.xml"))
		plex = self.newPlex()
		fullList, mediaContainer = plex.getShowsFromSection(
			"http://%s/library/sections/2/all" % self.mock.address)

		self.assertEqual(mediaContainer["title2"], "All Shows")
		self.assertEqual(len(fullList), 2)

		alpha = self.findEntry(fullList, "Alpha Show")
		self.assertEqual(alpha[1]["nextViewMode"], "ShowSeasons")
		self.assertEqual(alpha[3], "started")  # 3 of 10 episodes seen

		beta = self.findEntry(fullList, "Beta Show")
		self.assertEqual(beta[3], "seen")  # 8 of 8 episodes seen


class TestPlexMockInfrastructure(MockedPMSTestCase):
	"""The mock itself must slice paginated containers correctly."""

	def test_paged_route_honours_container_headers(self):
		items = ['<Video ratingKey="%d" title="Movie %d"/>' % (i, i) for i in range(5)]
		self.mock.add_paged("/library/sections/1/all", items, attrs={"title2": "All Movies"})

		request = Request("http://%s/library/sections/1/all" % self.mock.address)
		request.add_header("X-Plex-Container-Start", "2")
		request.add_header("X-Plex-Container-Size", "2")
		body = urlopen(request).read().decode("utf-8")

		import xml.etree.ElementTree as etree
		tree = etree.fromstring(body)
		self.assertEqual(tree.get("size"), "2")
		self.assertEqual(tree.get("totalSize"), "5")
		self.assertEqual(tree.get("offset"), "2")
		self.assertEqual(tree.get("title2"), "All Movies")
		videos = tree.findall("Video")
		self.assertEqual([v.get("ratingKey") for v in videos], ["2", "3"])

	def test_redirect_route(self):
		self.mock.add_xml("/target", "<MediaContainer size=\"0\"/>")
		self.mock.add_redirect("/moved", "/target", status=302)

		# urllib follows the redirect transparently
		body = urlopen("http://%s/moved" % self.mock.address).read().decode("utf-8")
		self.assertIn("MediaContainer", body)
		paths = [r["path"] for r in self.mock.requests]
		self.assertEqual(paths, ["/moved", "/target"])


if __name__ == "__main__":
	unittest.main()
