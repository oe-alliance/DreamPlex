# -*- coding: utf-8 -*-
"""Waking a server must not freeze the GUI.

sleepNow() is reached from a MessageBox callback, so it runs on the enigma2
main loop. It used to hold a time.sleep(wol_delay) - 60 seconds by default
and up to 180 - which blocks everything: no key is processed, and a block
that long is what the image's hang detector kills enigma2 for.

Checked on the source: DP_MainMenu pulls in enigma2, so it cannot be
imported offline.

Found while chasing the DreamFin report about the blue button; the scale
(default 60, not 10) came back from them.
"""

import ast
import re
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
MAINMENU = os.path.join(SRC, "DP_MainMenu.py")
INIT = os.path.join(SRC, "__init__.py")


def readSource(path):
	handle = io.open(path, "rb")
	try:
		return handle.read()
	finally:
		handle.close()


def findFunction(name):
	tree = ast.parse(readSource(MAINMENU), filename=MAINMENU)
	for node in ast.walk(tree):
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node

	raise AssertionError("%s() not found in DP_MainMenu.py" % name)


def calledNames(node):
	names = set()
	for child in ast.walk(node):
		if isinstance(child, ast.Call):
			names.add(getattr(child.func, "id", None) or getattr(child.func, "attr", None))

	return names


class TestWakeOnLanDoesNotBlock(unittest.TestCase):
	def test_no_sleep_while_waiting_for_the_server(self):
		sleepNow = findFunction("sleepNow")

		self.assertNotIn("sleep", calledNames(sleepNow),
				"sleepNow() runs on the main loop: sleeping here freezes the "
				"GUI for the whole wol_delay")

	def test_waits_with_a_timer_instead(self):
		sleepNow = findFunction("sleepNow")

		self.assertIn("eTimer", calledNames(sleepNow),
				"the wait has to be handed to a timer")

	def test_the_timer_is_imported(self):
		# DP_MainMenu had no `from enigma` import at all, so using eTimer
		# without adding it would only blow up on a real Wake on Lan - a
		# path almost nobody exercises (caught by DreamFin)
		source = readSource(MAINMENU).decode("utf-8")

		self.assertIn("from enigma import eTimer", source)

	def test_the_server_is_still_checked_afterwards(self):
		# the point of the wait is to look at the server again
		names = calledNames(findFunction("sleepNow"))
		names |= calledNames(findFunction("wolDelayElapsed"))

		self.assertIn("checkServerState", names)

	def test_a_live_timer_is_never_replaced(self):
		sleepNow = findFunction("sleepNow")

		guarded = False
		for node in ast.walk(sleepNow):
			if not isinstance(node, ast.If):
				continue
			condition = ast.dump(node.test)
			if "wolTimer" not in condition or "None" not in condition:
				continue
			if any(isinstance(c, ast.Call) and getattr(c.func, "id", None) == "eTimer"
					for c in ast.walk(node)):
				guarded = True

		self.assertTrue(guarded,
				"building a new eTimer over a live one drops the last "
				"reference to it while its callback may be on the stack")


class TestTheMessageDoesNotPromiseASpinner(unittest.TestCase):
	"""There is no spinner on this path, and the delay must leave the msgid.

	Wrapping a concatenation in _() builds the msgid with the number already
	in it, so it never matches the catalogue and the message always came out
	in English - the same mistake as the "All Pel·lis" filter label.
	"""

	def test_no_spinner_is_promised(self):
		source = readSource(MAINMENU).decode("utf-8")

		self.assertNotIn("spinner will run", source)

	def test_the_delay_is_interpolated_outside_the_translation(self):
		source = readSource(MAINMENU).decode("utf-8")

		self.assertIn("for the server to start up", source)
		self.assertNotIn('seconds. \\nAccording to your settings.") ', source)
		# the number goes in with %, not by building the msgid
		self.assertIn(') % self.g_woldelay', source)


class TestTheMessageActuallyReachesTheCatalogue(unittest.TestCase):
	"""The msgid the code asks for at runtime must exist in the catalogue.

	This is the check that would have caught the original bug: the string
	was translated in several languages and none of them ever showed,
	because the msgid was built by concatenation and carried the number.
	"""

	PO = os.path.join(os.path.dirname(SRC), "po")

	def runtimeMsgid(self):
		source = readSource(MAINMENU).decode("utf-8")
		match = re.search(r'message = _\("(.*?)"\) % self\.g_woldelay', source, re.S)
		self.assertIsNotNone(match, "the Wake on Lan message changed shape")

		return match.group(1).encode().decode("unicode_escape")

	def catalogueMsgids(self, path):
		msgids, current, inside = [], None, False
		for line in io.open(path, encoding="utf-8"):
			stripped = line.strip()
			if stripped.startswith("msgid "):
				if current is not None:
					msgids.append(current)
				current, inside = stripped[6:].strip('"'), True
			elif stripped.startswith("msgstr"):
				if current is not None:
					msgids.append(current)
					current = None
				inside = False
			elif inside and current is not None and stripped.startswith('"'):
				current += stripped.strip('"')

		if current is not None:
			msgids.append(current)

		return [m.encode().decode("unicode_escape") for m in msgids]

	def test_the_spanish_catalogue_can_translate_it(self):
		wanted = self.runtimeMsgid()
		msgids = self.catalogueMsgids(os.path.join(self.PO, "es.po"))

		self.assertIn(wanted, msgids,
				"the msgid asked for at runtime is not in es.po, so the "
				"message will never be translated")

	def test_the_delay_is_a_placeholder_not_part_of_the_msgid(self):
		wanted = self.runtimeMsgid()

		self.assertIn("%s", wanted,
				"the number must be a placeholder; baking it into the msgid "
				"is what made this string untranslatable")


class TestDiscoveryDoesNotBlock(unittest.TestCase):
	"""The LAN search is an ActionMap callback: it runs on the main loop."""

	SERVER = os.path.join(SRC, "DP_Server.py")

	def _function(self, name):
		tree = ast.parse(readSource(self.SERVER), filename=self.SERVER)
		for node in ast.walk(tree):
			if isinstance(node, ast.FunctionDef) and node.name == name:
				return node

		raise AssertionError("%s() not found in DP_Server.py" % name)

	def test_no_sleep_loop_waiting_for_the_search(self):
		keyBlue = self._function("keyBlue")

		self.assertNotIn("sleep", calledNames(keyBlue),
				"keyBlue() runs on the main loop: sleeping here freezes the GUI "
				"until the search answers, and for ever if it never does")

		loops = [n for n in ast.walk(keyBlue) if isinstance(n, (ast.While, ast.For))]
		self.assertEqual(loops, [], "the wait belongs to a timer, not to a loop")

	def test_the_search_is_capped(self):
		source = readSource(self.SERVER).decode("utf-8")

		self.assertIn("GDM_MAX_ATTEMPTS", source,
				"a silent GDM must not leave the timer polling for ever")

	def test_the_timer_is_imported_and_stopped(self):
		source = readSource(self.SERVER).decode("utf-8")
		self.assertIn("from enigma import eTimer", source)

		check = self._function("checkDiscovery")
		stops = [n for n in ast.walk(check)
				if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "stop"]
		self.assertTrue(stops, "checkDiscovery() must stop the timer when done")


class TestTheDelayIsAsLongAsDocumented(unittest.TestCase):
	"""Guards the reasoning above: this is a minute, not a moment."""

	def test_default_delay_is_the_one_we_reasoned_about(self):
		source = readSource(INIT).decode("utf-8")

		self.assertIn("wol_delay = ConfigInteger(default=60, limits=(1, 180))", source,
				"if this default changes, revisit how bad a blocking wait is")


if __name__ == "__main__":
	unittest.main()
