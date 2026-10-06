# -*- coding: utf-8 -*-
"""A msgid must be a literal, or the catalogue can never hold it.

`_("prefix " + value)` concatenates BEFORE gettext is called, so the key
looked up at runtime carries the value and matches nothing. The string is
untranslatable by construction, and the giveaway on screen is a label in
two languages at once - an English wrapper around a translated value, e.g.
"playback mode 'Transcodificado'", because the inner value is marked
separately and *is* found.

This rejects exactly that shape and deliberately says nothing about
`_(variable)`, which is fine: gettext returns the argument unchanged when
there is no entry, and most of those are names coming from the server.
Flagging them would drown the real defect in noise.

Guard ported from the DreamFin fork, which hit the same bug.

NOTE for anyone touching this: the AST node names differ between the two
interpreters the suite runs under. `ast.Str` is gone in 3.12+, `ast.Constant`
does not exist in 2.7, and `ast.JoinedStr` (f-strings) only from 3.6. The
`getattr(ast, "X", ())` dance below is what keeps it working on both:
isinstance(x, ()) is always False, so a missing node type becomes an empty
branch instead of an AttributeError.
"""

import ast
import glob
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

STR_NODE = getattr(ast, "Str", ())
CONSTANT_NODE = getattr(ast, "Constant", ())
FSTRING_NODE = getattr(ast, "JoinedStr", ())


def isStringLiteral(node):
	if CONSTANT_NODE and isinstance(node, CONSTANT_NODE):
		return isinstance(node.value, str)

	return bool(STR_NODE and isinstance(node, STR_NODE))


def inspectMsgids(path):
	"""((line, why) for every runtime-built msgid, how many _() calls were seen).

	The second number matters as much as the first: a walk that stops matching
	_() reports no offenders and looks exactly like a clean tree.
	"""
	handle = io.open(path, "rb")
	try:
		tree = ast.parse(handle.read(), filename=path)
	finally:
		handle.close()

	broken = []
	inspected = 0
	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		if getattr(node.func, "id", None) != "_" or not node.args:
			continue

		inspected += 1
		argument = node.args[0]
		if isStringLiteral(argument):
			continue  # the good case

		if FSTRING_NODE and isinstance(argument, FSTRING_NODE):
			broken.append((node.lineno, "f-string"))
			continue

		# a literal buried inside means it was glued to something at runtime
		if any(isStringLiteral(child) for child in ast.walk(argument)):
			broken.append((node.lineno, "literal joined to a value"))

	return broken, inspected


def brokenMsgids(path):
	"""(line, why) for every _() whose msgid is built at runtime."""
	return inspectMsgids(path)[0]


def sweepSource():
	"""(offenders, how many _() calls the walk actually looked at)."""
	offenders = []
	inspected = 0
	for path in sorted(glob.glob(os.path.join(SRC, "*.py"))):
		broken, seen = inspectMsgids(path)
		inspected += seen
		for line, why in broken:
			offenders.append("%s:%s (%s)" % (os.path.basename(path), line, why))

	return offenders, inspected


class TestMsgidsAreLiterals(unittest.TestCase):
	def test_no_msgid_is_built_at_runtime(self):
		offenders, inspected = sweepSource()

		self.assertEqual(offenders, [],
				"these msgids are assembled at runtime, so no catalogue entry "
				"can ever match them - pass the value with %% instead "
				"(%d _() calls inspected):\n  " % inspected
				+ "\n  ".join(offenders))


class TestTheSweepStillSeesTheCode(unittest.TestCase):
	"""Report how much was looked at, not just what was found.

	If the walk ever stops matching _() - the helper renamed, imported under
	another name, called as a method - this file reports no offenders and goes
	green while inspecting nothing at all. That passes for the wrong reason and
	looks identical to passing for the right one.

	Idea from the DreamFin fork, including the part that makes it useful: put
	the count in the message, so "no problems" can be told apart from "did not
	look". It is the same rule we keep repeating for ourselves - print where
	the number came from, not just the number - applied to the guard itself.
	"""

	def test_it_still_finds_calls_to_inspect(self):
		_offenders, inspected = sweepSource()

		self.assertGreater(inspected, 100,
				"only %d _() calls were inspected across src/, which means the "
				"walk has most likely stopped matching them rather than that "
				"the tree is clean" % inspected)


class TestTheDetectorWorks(unittest.TestCase):
	"""A guard that never fires is worth nothing."""

	def _scan(self, source):
		path = os.path.join(SRC, "__init__.py")  # any real path, only for the message
		tree = ast.parse(source, filename=path)
		found = []
		for node in ast.walk(tree):
			if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args:
				argument = node.args[0]
				if isStringLiteral(argument):
					continue
				if any(isStringLiteral(child) for child in ast.walk(argument)):
					found.append(node.lineno)

		return found

	def test_it_catches_concatenation(self):
		self.assertEqual(self._scan('_("mode \'" + name + "\'")\n'), [1])

	def test_it_catches_percent_applied_too_early(self):
		self.assertEqual(self._scan('_("error: %s" % err)\n'), [1])

	def test_it_stays_quiet_on_a_plain_literal(self):
		self.assertEqual(self._scan('_("Transcoded")\n'), [])

	def test_it_stays_quiet_on_a_bare_variable(self):
		# gettext returns it unchanged when there is no entry: harmless
		self.assertEqual(self._scan('_(title)\n'), [])

	def test_it_stays_quiet_on_the_correct_form(self):
		self.assertEqual(self._scan('_("mode \'%s\'") % name\n'), [])


if __name__ == "__main__":
	unittest.main()
