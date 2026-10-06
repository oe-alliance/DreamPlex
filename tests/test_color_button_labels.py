# -*- coding: utf-8 -*-
"""Every colour-button label is on screen, so every one of them must be marked.

setColorFunction() takes the text that ends up under the red/green/yellow/blue
button at the bottom of the library view. Three of them shipped as bare
literals for years - "refresh Library", "Server Settings", "Plex Settings" -
sitting between neighbours that were marked, which is exactly why nobody
noticed: the row read half in Spanish and half in English and looked like an
ordinary missing translation rather than a string the catalogue was never
asked about.

An empty label is fine and means the caller sets it later from code
(toggleFastScroll and friends do that). Anything else that reaches the screen
has to go through _().

This is the same family as test_gettext_msgids and test_gettext_sentinels, but
narrowed to one call whose whole purpose is to put text on screen - which
makes it the cheapest of the three to keep honest: there is no argument about
whether the string is user-visible.
"""

import ast
import glob
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

STR_NODE = getattr(ast, "Str", ())
CONSTANT_NODE = getattr(ast, "Constant", ())


def literalOf(node):
	if CONSTANT_NODE and isinstance(node, CONSTANT_NODE):
		return node.value if isinstance(node.value, str) else None

	if STR_NODE and isinstance(node, STR_NODE):
		return node.s

	return None


def isMarked(node):
	"""True when the label passes through _() somewhere."""
	for child in ast.walk(node):
		if isinstance(child, ast.Call) and getattr(child.func, "id", None) == "_":
			return True

	return False


def classifyLabels(path):
	"""(bare, marked, empty) for every setColorFunction label in a file."""
	handle = io.open(path, "rb")
	try:
		tree = ast.parse(handle.read(), filename=path)
	finally:
		handle.close()

	bare, marked, empty = [], [], []
	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		if getattr(node.func, "attr", None) != "setColorFunction":
			continue

		for keyword in node.keywords:
			if keyword.arg != "functionList":
				continue
			if not isinstance(keyword.value, ast.Tuple) or not keyword.value.elts:
				continue

			label = keyword.value.elts[0]
			text = literalOf(label)
			if text == "":
				empty.append((node.lineno, text))  # set later from code, on purpose
			elif isMarked(label):
				marked.append((node.lineno, text))
			else:
				bare.append((node.lineno, text))

	return bare, marked, empty


def bareLabels(path):
	"""(line, text) for every setColorFunction label that skips _()."""
	return classifyLabels(path)[0]


class TestColourButtonLabels(unittest.TestCase):
	def test_every_button_label_is_translatable(self):
		offenders = []
		for path in sorted(glob.glob(os.path.join(SRC, "*.py"))):
			for line, text in bareLabels(path):
				offenders.append("%s:%s %r" % (os.path.basename(path), line, text))

		self.assertEqual(offenders, [],
				"these go under a colour button and never reach the catalogue:\n  "
				+ "\n  ".join(offenders))


class TestTheSweepStillSeesTheCode(unittest.TestCase):
	"""A guard that stops looking passes for the wrong reason.

	If setColorFunction is ever renamed, or the label stops being the first
	element of the functionList tuple, the walk above matches nothing and the
	test above goes green while checking exactly zero labels - and nobody
	notices, because a passing test looks the same either way. So require the
	sweep to keep finding the shapes we know are there.

	Idea from the DreamFin fork, who added it to their copy of this guard.
	"""

	def _sweep(self):
		bare, marked, empty = [], [], []
		for path in sorted(glob.glob(os.path.join(SRC, "*.py"))):
			b, m, e = classifyLabels(path)
			bare += b
			marked += m
			empty += e

		return bare, marked, empty

	def test_it_still_finds_labels_that_are_marked(self):
		_bare, marked, _empty = self._sweep()

		self.assertGreaterEqual(len(marked), 5,
				"the sweep collected %d marked labels, so it has most likely "
				"stopped matching setColorFunction rather than found a clean tree"
				% len(marked))

	def test_it_still_finds_labels_left_empty_on_purpose(self):
		_bare, _marked, empty = self._sweep()

		self.assertGreaterEqual(len(empty), 5,
				"the sweep collected %d dynamic labels - same suspicion"
				% len(empty))


class TestTheDetectorWorks(unittest.TestCase):
	"""A guard that never fires is worth nothing."""

	def _scan(self, source):
		tree = ast.parse(source, filename="<test>")
		found = []
		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			if getattr(node.func, "attr", None) != "setColorFunction":
				continue
			for keyword in node.keywords:
				if keyword.arg != "functionList":
					continue
				if not isinstance(keyword.value, ast.Tuple) or not keyword.value.elts:
					continue
				label = keyword.value.elts[0]
				if literalOf(label) == "":
					continue
				if not isMarked(label):
					found.append(node.lineno)

		return found

	def test_it_catches_a_bare_label(self):
		source = 'self.setColorFunction(color="red", level="3", functionList=("Server Settings", self.x))\n'
		self.assertEqual(self._scan(source), [1])

	def test_it_accepts_a_marked_label(self):
		source = 'self.setColorFunction(color="red", level="3", functionList=(_("Server Settings"), self.x))\n'
		self.assertEqual(self._scan(source), [])

	def test_it_accepts_a_label_built_around_a_marked_part(self):
		source = 'self.setColorFunction(color="red", level="2", functionList=(_("View \'") + name + " \'", self.x))\n'
		self.assertEqual(self._scan(source), [])

	def test_an_empty_label_is_allowed(self):
		source = 'self.setColorFunction(color="green", level="1", functionList=("", self.x))\n'
		self.assertEqual(self._scan(source), [])


if __name__ == "__main__":
	unittest.main()
