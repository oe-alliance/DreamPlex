# -*- coding: utf-8 -*-
"""Every stdlib import in src/ must resolve on the running interpreter.

This is the check that would have caught the OpenATV 8.0 outage: URLopener was
removed in Python 3.14 and both branches of DP_Syncer's try/except pointed at
the same removed symbol, so the import raised - and because DreamPlex is an
Autostart plugin, enigma2 itself refused to start.

Byte-compiling (tools/run_checks.py) does NOT catch this: the syntax is valid,
the symbol only fails to exist at import time. Importing the modules outright
would drag in all of enigma2, so instead we read the imports statically and
resolve only the standard-library ones, honouring try/except fallbacks (a
py2/py3 pair is fine as long as ONE branch works on this interpreter).
"""

import ast
import os
import unittest

try:
	from tests import helpers
except ImportError:  # direct invocation from the tests directory
	import helpers

helpers.setup_environment()

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

# the receiver environment and third-party packages: not our business here,
# and not installed on a dev machine
ENVIRONMENT_ROOTS = set([
	"enigma", "Components", "Screens", "Tools", "Plugins", "skin",
	"twisted", "six", "boxbranding",
])


# py3 has ast.Try; py2 splits it into TryExcept/TryFinally
BRANCHING_NODES = tuple(
	getattr(ast, name) for name in ("Try", "TryExcept", "TryFinally", "If")
	if hasattr(ast, name))


def _is_environment(module):
	return module.split(".")[0] in ENVIRONMENT_ROOTS


def _import_targets(node):
	"""(module, fromlist) pairs an Import/ImportFrom node needs at runtime."""
	if isinstance(node, ast.Import):
		return [(alias.name, []) for alias in node.names]
	if isinstance(node, ast.ImportFrom):
		if node.level:            # relative import: our own package
			return []
		return [(node.module, [alias.name for alias in node.names])]
	return []


def _groups(tree):
	"""Alternative-groups of the imports executed when the module is imported.

	Only module level counts: those are the ones that abort the import - and,
	for an Autostart plugin, boot. Imports inside functions are deferred and
	usually guarded (e.g. `if PY2: import commands`), so they are out of scope.

	A try/except or an if/else at module level yields ONE group holding every
	import in its branches: a py2/py3 pair only needs one branch to work.
	Anything else is a group of its own and must resolve.
	"""
	groups = []

	for node in tree.body:
		if isinstance(node, (ast.Import, ast.ImportFrom)):
			for target in _import_targets(node):
				groups.append([target])

		elif isinstance(node, BRANCHING_NODES):
			alternatives = []
			for child in ast.walk(node):
				if isinstance(child, (ast.Import, ast.ImportFrom)):
					alternatives.extend(_import_targets(child))
			if alternatives:
				groups.append(alternatives)

	return groups


def _resolves(module, fromlist):
	try:
		imported = __import__(module, {}, {}, list(fromlist) or [])
	except Exception:
		return False
	for name in fromlist:
		if name == "*":
			continue
		if not hasattr(imported, name):
			# submodule import (from pkg import module) is fine too
			try:
				__import__(module + "." + name)
			except Exception:
				return False
	return True


class TestAutostartIsGuarded(unittest.TestCase):
	"""The boot entry points must never let an exception reach enigma2.

	Autostart() runs while enigma2 reads the plugin list at boot: anything
	escaping it takes the GUI down and leaves the receiver in a respawn loop.
	Checked statically so the guard cannot be removed unnoticed (importing
	plugin.py here would pull in most of enigma2).
	"""

	def _function(self, tree, name):
		for node in ast.walk(tree):
			if isinstance(node, ast.FunctionDef) and node.name == name:
				return node
		self.fail("%s() not found in plugin.py" % name)

	def _calls_inside_try(self, func, callee):
		"""Is every call to `callee` inside a try block of this function?"""
		guarded, total = 0, 0
		for node in ast.walk(func):
			if isinstance(node, BRANCHING_NODES) and not isinstance(node, ast.If):
				for child in ast.walk(node):
					if (isinstance(child, ast.Call) and
							isinstance(child.func, ast.Name) and child.func.id == callee):
						guarded += 1
		for node in ast.walk(func):
			if (isinstance(node, ast.Call) and
					isinstance(node.func, ast.Name) and node.func.id == callee):
				total += 1
		return total > 0 and guarded == total

	def test_boot_entry_points_are_wrapped(self):
		path = os.path.join(os.path.dirname(SRC), "src", "plugin.py")
		with open(path, "rb") as handle:
			tree = ast.parse(handle.read(), filename=path)

		autostart = self._function(tree, "Autostart")
		self.assertTrue(
			self._calls_inside_try(autostart, "prepareEnvironment"),
			"Autostart() must call prepareEnvironment() inside a try/except, "
			"otherwise a plugin failure stops enigma2 from booting")

		session_start = self._function(tree, "sessionStart")
		self.assertTrue(
			self._calls_inside_try(session_start, "startEnvironment"),
			"sessionStart() must call startEnvironment() inside a try/except")


class TestStdlibImports(unittest.TestCase):
	def test_every_stdlib_import_resolves(self):
		failures = []

		for name in sorted(os.listdir(SRC)):
			if not name.endswith(".py"):
				continue
			path = os.path.join(SRC, name)
			# read bytes: on py2 ast.parse() rejects a unicode string that
			# carries a coding declaration
			with open(path, "rb") as handle:
				source = handle.read()
			tree = ast.parse(source, filename=path)

			for alternatives in _groups(tree):
				stdlib = [(m, f) for (m, f) in alternatives if m and not _is_environment(m)]
				if not stdlib:
					continue
				if not any(_resolves(m, f) for (m, f) in stdlib):
					wanted = ", ".join(
						"%s%s" % (m, (" (" + ", ".join(f) + ")") if f else "")
						for (m, f) in stdlib)
					failures.append("%s: no usable import among -> %s" % (name, wanted))

		self.assertEqual(failures, [], "unresolvable stdlib imports:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
	unittest.main()
