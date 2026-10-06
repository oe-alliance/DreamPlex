# -*- coding: utf-8 -*-
"""Editing a plex.tv server that was provisioned with a token.

A provisioning system can write `myplexToken` (+ `machineIdentifier`) into
the settings and deliberately leave `myplexPassword` empty, so the customer's
password never reaches the box. Runtime honours that (setMyPlexData keeps an
existing token), but saving the server from the GUI used to sign in again
unconditionally and failed with "Invalid email, username, or password",
losing the edit.
"""

import ast
import os
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


class TestMissingCredentialsGuard(unittest.TestCase):
	"""getNewMyPlexToken() must not try to sign in without credentials."""

	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)

	def test_empty_password_is_refused_without_a_request(self):
		# the old guard `(user or password) == ""` evaluated the username,
		# so this went out as Basic base64("user:") and earned a 401
		plex = helpers.make_plex_instance(mock=self.mock,
				myplexUsername="someone", myplexPassword="")

		self.assertFalse(plex.getNewMyPlexToken())
		self.assertIn("missing", plex.getLastResponse().lower())

	def test_empty_username_is_refused_too(self):
		plex = helpers.make_plex_instance(mock=self.mock,
				myplexUsername="", myplexPassword="secret")

		self.assertFalse(plex.getNewMyPlexToken())
		self.assertIn("missing", plex.getLastResponse().lower())


class TestSaveDoesNotReauthenticate(unittest.TestCase):
	"""keySave() may only sign in again when there is no token yet.

	Checked on the source: instantiating the settings screen would need a
	live enigma2 session, but the decision itself is a plain condition.
	"""

	def _keySave(self):
		path = os.path.join(SRC, "DP_Server.py")
		with open(path, "rb") as handle:
			tree = ast.parse(handle.read(), filename=path)
		for node in ast.walk(tree):
			if isinstance(node, ast.FunctionDef) and node.name == "keySave":
				return node
		self.fail("keySave() not found")

	def test_relogin_is_conditional_on_a_missing_token(self):
		source = ast.dump(self._keySave())

		# the guard has to look at myplexToken, otherwise every save
		# re-authenticates and provisioned servers cannot be edited
		self.assertIn("myplexToken", source,
				"keySave() must check myplexToken before signing in again")
		self.assertIn("keyBlue", source)
		self.assertIn("saveNow", source)


class TestTokenIsVisible(unittest.TestCase):
	def test_token_has_a_settings_entry(self):
		path = os.path.join(SRC, "DP_Server.py")
		with open(path, "rb") as handle:
			source = handle.read().decode("utf-8")

		# without an entry the token cannot be checked, pasted or cleared
		self.assertIn("self.current.myplexToken", source)


if __name__ == "__main__":
	unittest.main()
