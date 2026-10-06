# -*- coding: utf-8 -*-
"""_() must not depend on startup order to find its own catalogue.

localeInit() binds the DreamPlex text domain, and it runs from
prepareEnvironment(), which enigma2 calls from the Autostart callback. But
enigma2 calls Plugins() to read the plugin list BEFORE any of that, so every
string translated at registration time asked gettext for a domain that was
not bound yet and got the msgid straight back. Proved on the receiver:

    without bindtextdomain -> 'plex client for enigma2'
    with    bindtextdomain -> 'Un cliente Plex para Enigma2'

which is why the plugin browser kept showing English while the .mo shipped in
the package translated the string perfectly. Three things were checked before
that - catalogue rebuilt, entry present, entry actually translated - and all
three passed. The fourth only shows up at runtime: the domain has to be bound
when the call is made.

So _() binds on first use. These tests hold that behaviour in place, and in
particular that a failure to bind is swallowed: the worst case has to stay
what it already was, never an exception thrown at enigma2 while it is reading
the plugin list.
"""

import gettext
import unittest

try:
	from tests import helpers
except ImportError:
	import helpers

setup_environment = helpers.setup_environment


class TestLocaleBinding(unittest.TestCase):
	def setUp(self):
		setup_environment()
		import src

		self.src = src
		self.originalBind = gettext.bindtextdomain
		self.originalTried = src._localeBindTried
		self.calls = []

	def tearDown(self):
		gettext.bindtextdomain = self.originalBind
		self.src._localeBindTried = self.originalTried

	def _recordBinds(self, raises=None):
		def fake(domain, directory=None):
			self.calls.append((domain, directory))
			if raises is not None:
				raise raises

			return directory

		gettext.bindtextdomain = fake

	def test_it_binds_our_domain_on_the_first_translation(self):
		self._recordBinds()
		self.src._localeBindTried = False

		self.src._("anything")

		self.assertEqual([domain for domain, _directory in self.calls], ["DreamPlex"],
				"_() has to bind its own catalogue before looking anything up, or "
				"it returns the msgid whenever it runs before localeInit()")

	def test_it_points_at_the_plugin_locale_directory(self):
		self._recordBinds()
		self.src._localeBindTried = False

		self.src._("anything")

		self.assertTrue(self.calls[0][1].endswith("Extensions/DreamPlex/locale/"),
				"bound the wrong directory: %r" % (self.calls[0][1],))

	def test_it_binds_once_and_not_on_every_lookup(self):
		self._recordBinds()
		self.src._localeBindTried = False

		for _each in range(5):
			self.src._("anything")

		self.assertEqual(len(self.calls), 1,
				"_() is called constantly while drawing a library view; binding "
				"on every lookup would be pure waste")

	def test_a_failure_to_bind_never_escapes(self):
		self._recordBinds(raises=OSError("no such directory"))
		self.src._localeBindTried = False

		# this runs while enigma2 reads the plugin list, where Plugins() has no
		# try/except of its own - an exception here must not reach it
		result = self.src._("anything")

		self.assertEqual(result, "anything",
				"when the catalogue cannot be bound the answer must be the msgid, "
				"exactly what happened before this existed")

	def test_a_failed_bind_is_not_retried_forever(self):
		self._recordBinds(raises=OSError("no such directory"))
		self.src._localeBindTried = False

		for _each in range(5):
			self.src._("anything")

		self.assertEqual(len(self.calls), 1,
				"the flag has to be set before the risky call, or a permanent "
				"failure means retrying on every single translation")

	def test_the_empty_string_stays_empty(self):
		self._recordBinds()
		self.src._localeBindTried = False

		self.assertEqual(self.src._(""), "")


if __name__ == "__main__":
	unittest.main()
