# -*- coding: utf-8 -*-
"""A translated string must never double as a sentinel.

The mirror image of test_gettext_msgids: there the bug is a missing `_()`,
here it is an `_()` that should not be there. If a literal is marked for
translation in one place and compared against in another, the comparison
stops matching the moment somebody translates it - and it fails ONLY in the
translated languages, so it survives every test run in English.

The one this caught: DP_Player.py set `myLanguage = _("<unknown>")` and later
asked `if myLanguage == "<unknown>"` to decide whether to auto-enable external
forced subtitles. es.po translates it to "<desconocido>" and fr.po to
"<inconnu>", so that branch was dead in both languages and alive in English.

Comparisons against values that come from the SERVER are fine and must stay
quiet, or the guard drowns in noise: the Plex API always answers in English,
so `mediaContainer.get("title2") != "By Folder"` is correct even though
DPH_Translations.py marks "By Folder" for the translators. Same for the
media types ("Season", "Music") and for menu keys that are stored as data
next to their own translated label, like ("LiveTv" -> _("LiveTv")).

Rule ported from the DreamFin fork's "marked here, bare there" sweep - this
is the same idea narrowed to comparisons, which is where it stops being
cosmetic and starts changing behaviour.

See the note in test_gettext_msgids.py about AST node names differing
between the two interpreters this suite runs under.
"""

import ast
import glob
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

STR_NODE = getattr(ast, "Str", ())
CONSTANT_NODE = getattr(ast, "Constant", ())

# Literals that legitimately appear both marked and compared. Each one is a
# value that arrives from outside already in English, or a key stored as data.
#
# Write the real reason next to every entry, and check it against the code
# before adding one. An exception added to silence a report is the one that
# hides the next bug: the DreamFin fork's sweep DID flag their "<unknown>"
# and it was whitelisted as "a fallback value, not screen text" - which
# sounded right and was wrong. The plausible label is the danger.
ALLOWED = set([
	"By Folder",   # mediaContainer["title2"], straight from the Plex API
	"Season",      # media type from the API
	"Music",       # media type from the API
	"LiveTv",      # menu key stored beside its own translated label
	" ",           # NOT a shared string: the comparison is against
	               # onNumberKeyLastChar, a character typed on the remote, and
	               # the marked one is a config-list help text that happens to
	               # be a single space. They collide by coincidence.
])


def literalOf(node):
	if CONSTANT_NODE and isinstance(node, CONSTANT_NODE):
		return node.value if isinstance(node.value, str) else None

	if STR_NODE and isinstance(node, STR_NODE):
		return node.s

	return None


def markedLiterals(trees):
	"""Every literal that is a first argument of _()."""
	marked = {}
	for path, tree in trees:
		for node in ast.walk(tree):
			if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args:
				text = literalOf(node.args[0])
				if text:
					marked.setdefault(text, (os.path.basename(path), node.lineno))

	return marked


def comparedLiterals(trees, marked):
	"""(file, line, text) for every comparison against a translated literal."""
	found = []
	for path, tree in trees:
		for node in ast.walk(tree):
			if not isinstance(node, ast.Compare):
				continue

			for side in [node.left] + list(node.comparators):
				text = literalOf(side)
				if text is not None and text in marked and text not in ALLOWED:
					found.append((os.path.basename(path), node.lineno, text))

	return found


def parseSource():
	trees = []
	for path in sorted(glob.glob(os.path.join(SRC, "*.py"))):
		handle = io.open(path, "rb")
		try:
			trees.append((path, ast.parse(handle.read(), filename=path)))
		finally:
			handle.close()

	return trees


def countComparedLiterals(trees):
	"""How many literals sit in a comparison at all, allowed or not."""
	total = 0
	for _path, tree in trees:
		for node in ast.walk(tree):
			if not isinstance(node, ast.Compare):
				continue
			for side in [node.left] + list(node.comparators):
				if literalOf(side) is not None:
					total += 1

	return total


class TestNoTranslatedSentinels(unittest.TestCase):
	def test_no_comparison_against_a_translated_literal(self):
		trees = parseSource()
		marked = markedLiterals(trees)

		offenders = []
		for name, line, text in comparedLiterals(trees, marked):
			origin = marked[text]
			offenders.append("%s:%s compares %r, translated at %s:%s"
					% (name, line, text, origin[0], origin[1]))

		self.assertEqual(sorted(set(offenders)), [],
				"these comparisons break as soon as the string is translated, so "
				"they fail in every language except English (%d marked strings "
				"and %d compared literals seen):\n  "
				% (len(marked), countComparedLiterals(trees))
				+ "\n  ".join(sorted(set(offenders))))


class TestTheSweepStillSeesTheCode(unittest.TestCase):
	"""This guard needs BOTH halves of its walk to keep working.

	It compares two collections - strings marked with _(), and literals used as
	comparison operands - and reports where they overlap. If either half stops
	matching, the overlap is empty, no offender is reported and the test goes
	green having checked nothing. Neither failure has a symptom of its own.

	Idea from the DreamFin fork, along with putting the counts in the message
	so "no problems" can be told apart from "did not look".
	"""

	def test_it_still_collects_marked_strings(self):
		trees = parseSource()
		marked = markedLiterals(trees)

		self.assertGreater(len(marked), 100,
				"the walk collected %d marked strings, so it has most likely "
				"stopped matching _() rather than found a tree with none"
				% len(marked))

	def test_it_still_collects_compared_literals(self):
		trees = parseSource()

		self.assertGreater(countComparedLiterals(trees), 100,
				"the walk collected %d compared literals, so it has most likely "
				"stopped matching comparisons rather than found a tree with none"
				% countComparedLiterals(trees))


class TestTheDetectorWorks(unittest.TestCase):
	"""A guard that never fires is worth nothing."""

	def _scan(self, source):
		tree = ast.parse(source, filename="<test>")
		trees = [("<test>", tree)]
		marked = markedLiterals(trees)
		return [line for _name, line, _text in comparedLiterals(trees, marked)]

	def test_it_catches_the_subtitle_sentinel(self):
		source = 'a = _("<unknown>")\nif a == "<unknown>":\n\tpass\n'
		self.assertEqual(self._scan(source), [2])

	def test_it_catches_the_literal_on_the_left(self):
		source = 'a = _("<unknown>")\nif "<unknown>" == a:\n\tpass\n'
		self.assertEqual(self._scan(source), [2])

	def test_it_stays_quiet_when_nothing_translates_it(self):
		source = 'if myType == "Episode":\n\tpass\n'
		self.assertEqual(self._scan(source), [])

	def test_it_stays_quiet_on_an_allowed_value(self):
		source = 'a = _("By Folder")\nif container == "By Folder":\n\tpass\n'
		self.assertEqual(self._scan(source), [])


if __name__ == "__main__":
	unittest.main()
