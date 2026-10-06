# -*- coding: utf-8 -*-
"""The list handed to the player must match the list shown on screen.

DP_View keeps the browsable list twice: inside the listbox widget, and in
self.listViewList, which is what onEnter() hands to DP_Player together with
the WIDGET's index (self["listview"].getIndex()). If a code path repoints the
widget at a different list without repointing self.listViewList too, the two
drift apart and that index is applied to the wrong list:

	index past the end of the stale list -> IndexError in DP_Player.playMedia(),
		which takes enigma2 down with it;
	index still inside it -> a DIFFERENT item plays, silently. The worse of the
		two, because nobody reports it as a bug.

That is exactly what onLeave() did: going back up a level it restored the
widget from currentEntryDataDict but left self.listViewList pointing at the
level below. In mixed views (Recently Added / On Deck, which carry movies
next to shows) you could enter a show, walk down to its episodes, come back,
press OK on a movie - and play an episode, or crash. Reported by the DreamFin
project, which hit the crash in code identical to ours.

filter() already knew the rule; it carries the comment "we also have to reset
the variable because this one is passed to player". This guard applies the
rule to every call site instead of trusting whoever writes the next one.
"""

import ast
import os
import unittest

try:
	from tests import helpers
except ImportError:  # direct invocation from the tests directory
	import helpers

helpers.setup_environment()

VIEW = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "DP_View.py")

# the widget and the variable that must stay in step with it
WIDGET = "listview"
MIRROR = "listViewList"

# every setList call site known when this guard was written; if the scan ever
# finds fewer, it is the scan that broke, not the code that got tidier
KNOWN_CALL_SITES = 4


def _literal(node):
	"""The string behind a subscript key, across py2 and py3 ast shapes."""
	if hasattr(ast, "Constant") and isinstance(node, ast.Constant):
		return node.value if isinstance(node.value, str) else None
	if hasattr(ast, "Str") and isinstance(node, ast.Str):
		return node.s
	return None


def _subscript_key(node):
	"""self["listview"] -> "listview"; anything else -> None."""
	if not isinstance(node, ast.Subscript):
		return None
	if not (isinstance(node.value, ast.Name) and node.value.id == "self"):
		return None
	index = node.slice
	if hasattr(ast, "Index") and isinstance(index, ast.Index):  # py2, py3 < 3.9
		index = index.value
	return _literal(index)


def _is_self_attr(node, attr):
	"""True for self.<attr>."""
	return (isinstance(node, ast.Attribute) and node.attr == attr
			and isinstance(node.value, ast.Name) and node.value.id == "self")


class TestListViewStaysInSyncWithThePlayer(unittest.TestCase):
	def setUp(self):
		with open(VIEW) as handle:
			self.tree = ast.parse(handle.read())

	def _functions(self):
		for node in ast.walk(self.tree):
			if isinstance(node, ast.FunctionDef):
				yield node

	def _setlist_calls(self, func):
		"""Calls to self["listview"].setList(...) inside func."""
		for node in ast.walk(func):
			if not isinstance(node, ast.Call):
				continue
			callee = node.func
			if not (isinstance(callee, ast.Attribute) and callee.attr == "setList"):
				continue
			if _subscript_key(callee.value) != WIDGET:
				continue
			yield node

	def _assigns_mirror(self, func):
		"""True if func assigns self.listViewList anywhere."""
		for node in ast.walk(func):
			if not isinstance(node, ast.Assign):
				continue
			for target in node.targets:
				if _is_self_attr(target, MIRROR):
					return True
		return False

	def test_every_setlist_keeps_the_player_list_in_step(self):
		offenders = []
		examined = 0

		for func in self._functions():
			calls = list(self._setlist_calls(func))
			if not calls:
				continue
			syncs = self._assigns_mirror(func)
			for call in calls:
				examined += 1
				argument = call.args[0] if call.args else None
				# handing the widget self.listViewList itself cannot drift
				if _is_self_attr(argument, MIRROR):
					continue
				if not syncs:
					offenders.append("%s (line %d)" % (func.name, call.lineno))

		self.assertGreaterEqual(
			examined, KNOWN_CALL_SITES,
			"only found %d setList call sites, expected at least %d - the scan is "
			"broken, not the code" % (examined, KNOWN_CALL_SITES))

		self.assertEqual(
			offenders, [],
			"these repoint the %r widget at another list but leave self.%s stale, "
			"so onEnter() would hand DP_Player the wrong list: %s (checked %d call "
			"sites)" % (WIDGET, MIRROR, ", ".join(offenders), examined))

	def test_onleave_restores_the_player_list(self):
		"""The specific regression: coming back up a level must repoint it."""
		found = [f for f in self._functions() if f.name == "onLeave"]
		self.assertEqual(len(found), 1, "expected exactly one onLeave, found %d" % len(found))
		self.assertTrue(
			self._assigns_mirror(found[0]),
			"onLeave() restores the widget list but never reassigns self.%s: the "
			"player would be handed the previous level's list" % MIRROR)


if __name__ == "__main__":
	unittest.main()
