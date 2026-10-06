# -*- coding: utf-8 -*-
"""Syncer downloads, tested through downloadMedia() and nothing below it.

The image download has had two implementations. Upstream keeps URLopener at
its call sites and, since 226aa83, supplies a small replacement class where
Python 3.14 removed it; this fork replaced URLopener with urlopen/Request.
Both expose the same downloadMedia() and talk to the same collaborators - the
Plex instance for the server and its token, the server config for whether a
token is needed, the message pump for progress - and differ only in the
attribute they initialise lazily.

So these tests stay above that line on purpose. The same file passes against
either implementation, which is the evidence that swapping one for the other
loses nothing on the paths below: the bytes land in the file, the token
travels exactly when it is needed, a failed download is reported rather than
raised, and the connection is prepared once.

Worth knowing when reading a result: downloadMedia() swallows exceptions from
the transfer and reports "... failed" instead. A test that only checked that
nothing was raised would pass with a download that never happened, so every
case below also looks at what arrived - the file, or the request the server
recorded.
"""

import os
import shutil
import tempfile
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

from src.__init__ import _
from src.DP_Syncer import BackgroundMediaSyncer, THREAD_WORKING


class Value(object):
	def __init__(self, value):
		self.value = value


class ServerConfig(object):
	def __init__(self, connectionType, localAuth):
		self.connectionType = Value(connectionType)
		self.localAuth = Value(localAuth)


class PlexInstance(object):
	"""Only the two calls downloadMedia() makes."""

	def __init__(self, token):
		self.token = token
		self.serverLookups = 0

	def getServerFromURL(self, url):
		self.serverLookups += 1
		return "server-under-test"

	def get_hTokenForServer(self, server):
		# the real one returns None whenever the token is not cached
		if self.token is None:
			return None

		return {"X-Plex-Token": self.token}


class Messages(object):
	def __init__(self):
		self.pushed = []

	def push(self, message):
		self.pushed.append(message)


class MessagePump(object):
	def send(self, value):
		pass


class TestSyncerDownload(unittest.TestCase):
	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.tmp = tempfile.mkdtemp(prefix="dreamplex-syncer-")
		self.addCleanup(shutil.rmtree, self.tmp, True)

	def newSyncer(self, connectionType="0", localAuth=False, token="tok-123"):
		# BackgroundMediaSyncer is a Thread whose __init__ wires the whole
		# plugin up; build it bare and hand it only what downloadMedia() uses
		syncer = BackgroundMediaSyncer.__new__(BackgroundMediaSyncer)
		syncer.serverConfig = ServerConfig(connectionType, localAuth)
		syncer.plexInstance = PlexInstance(token)
		syncer.messages = Messages()
		syncer.messagePump = MessagePump()

		# one implementation initialises each of these lazily; setting both
		# keeps the test independent of which one it runs against
		syncer.urllibInstance = None
		syncer.downloadHeaders = None
		return syncer

	def url(self, path):
		return "http://%s%s" % (self.mock.address, path)

	def lastRequestToken(self):
		return self.mock.requests[-1]["headers"].get("x-plex-token")

	def test_downloads_the_bytes_to_the_file(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"BINARY-POSTER-DATA")
		syncer = self.newSyncer()
		target = os.path.join(self.tmp, "poster.jpg")

		syncer.downloadMedia(self.url("/photo/poster.jpg"), target, "100", "150")

		with open(target, "rb") as handle:
			self.assertEqual(handle.read(), b"BINARY-POSTER-DATA")

		self.assertEqual(syncer.messages.pushed[-1], (THREAD_WORKING, _("... success")))

	def test_sends_the_token_to_a_plex_tv_server(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"x")
		syncer = self.newSyncer(connectionType="2")

		syncer.downloadMedia(self.url("/photo/poster.jpg"), os.path.join(self.tmp, "p.jpg"), "100", "150")

		self.assertEqual(self.lastRequestToken(), "tok-123")

	def test_sends_the_token_with_local_auth(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"x")
		syncer = self.newSyncer(connectionType="0", localAuth=True)

		syncer.downloadMedia(self.url("/photo/poster.jpg"), os.path.join(self.tmp, "p.jpg"), "100", "150")

		self.assertEqual(self.lastRequestToken(), "tok-123")

	def test_sends_no_token_when_none_is_needed(self):
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"x")
		syncer = self.newSyncer(connectionType="0", localAuth=False)

		syncer.downloadMedia(self.url("/photo/poster.jpg"), os.path.join(self.tmp, "p.jpg"), "100", "150")

		self.assertIsNone(self.lastRequestToken())

	def test_reports_a_failed_download_instead_of_raising(self):
		syncer = self.newSyncer()
		target = os.path.join(self.tmp, "missing.jpg")

		syncer.downloadMedia(self.url("/photo/not-there.jpg"), target, "100", "150")

		self.assertEqual(self.mock.requests[-1]["path"].split("?")[0], "/photo/not-there.jpg",
				"the request never reached the server, so this proves nothing")
		self.assertEqual(syncer.messages.pushed[-1], (THREAD_WORKING, _("... failed")))

	def test_prepares_the_connection_only_once(self):
		self.mock.add_raw("/photo/a.jpg", "image/jpeg", b"a")
		self.mock.add_raw("/photo/b.jpg", "image/jpeg", b"b")
		syncer = self.newSyncer(connectionType="2")

		syncer.downloadMedia(self.url("/photo/a.jpg"), os.path.join(self.tmp, "a.jpg"), "100", "150")
		syncer.downloadMedia(self.url("/photo/b.jpg"), os.path.join(self.tmp, "b.jpg"), "100", "150")

		self.assertEqual(syncer.plexInstance.serverLookups, 1)
		self.assertEqual(self.lastRequestToken(), "tok-123",
				"the second download has to reuse the prepared token")


	def test_a_missing_token_does_not_crash_the_download(self):
		# get_hTokenForServer() returns None whenever the token is not cached.
		# Indexing that during the lazy set-up raised a TypeError BEFORE the
		# download's own try, so it escaped downloadMedia() and took the
		# syncer thread down instead of reporting anything.
		self.mock.add_raw("/photo/poster.jpg", "image/jpeg", b"x")
		syncer = self.newSyncer(connectionType="2", token=None)

		syncer.downloadMedia(self.url("/photo/poster.jpg"), os.path.join(self.tmp, "p.jpg"), "100", "150")

		self.assertEqual(len(self.mock.requests), 1, "the download never reached the server")
		self.assertIsNone(self.lastRequestToken())


if __name__ == "__main__":
	unittest.main()
