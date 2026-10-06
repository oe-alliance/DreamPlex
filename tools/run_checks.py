# -*- coding: utf-8 -*-
"""Offline gate for the dual py2/py3 requirement.

1. Byte-compiles every plugin module with the running interpreter.
2. Scans the files this fork touches for syntax that Python 2.7
   (OpenATV 6.4) cannot parse: f-strings, walrus, async/await,
   argument-less super(), nonlocal, ``yield from`` and annotations.

Run with:  py -3 tools/run_checks.py
"""

from __future__ import print_function

import os
import py_compile
import re
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# files this fork modifies and therefore must stay Python 2.7 compatible
PY2_GUARDED_FILES = [
	"src/DP_PlexLibrary.py",
	"src/DP_Server.py",
	"src/DP_View.py",
	"src/__init__.py",
	"src/__common__.py",
]

PY3_ONLY_PATTERNS = [
	(re.compile(r"(?<![\w.\"'])[rbuRBU]{0,2}[fF][rbuRBU]{0,2}[\"']"), "f-string literal"),
	(re.compile(r":="), "walrus operator"),
	(re.compile(r"\basync\s+def\b"), "async def"),
	(re.compile(r"\bawait\s"), "await"),
	(re.compile(r"\bnonlocal\b"), "nonlocal"),
	(re.compile(r"\byield\s+from\b"), "yield from"),
	(re.compile(r"\bsuper\(\)"), "argument-less super()"),
	(re.compile(r"^\s*def\s+\w+\s*\([^)]*\)\s*->"), "return annotation"),
]


def iter_python_files():
	for base in ("src", "tests", "tools"):
		for root, dirs, files in os.walk(os.path.join(REPO_ROOT, base)):
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			for name in sorted(files):
				if name.endswith(".py"):
					yield os.path.join(root, name)


def strip_comments_and_strings(line):
	"""Very light scrub so patterns don't fire inside comments."""
	hashPos = line.find("#")
	if hashPos != -1:
		line = line[:hashPos]
	return line


def check_compile():
	failures = []
	tmpdir = tempfile.mkdtemp(prefix="dreamplex-compile-")
	count = 0
	for path in iter_python_files():
		count += 1
		target = os.path.join(tmpdir, "out%d.pyc" % count)
		try:
			py_compile.compile(path, cfile=target, doraise=True)
		except py_compile.PyCompileError as error:
			failures.append("%s: %s" % (path, error.msg))
		try:
			if os.path.exists(target):
				os.remove(target)
		except OSError:
			pass
	try:
		os.rmdir(tmpdir)
	except OSError:
		pass
	return count, failures


def check_py2_syntax():
	failures = []
	for relative in PY2_GUARDED_FILES:
		path = os.path.join(REPO_ROOT, relative.replace("/", os.sep))
		if not os.path.exists(path):
			continue
		fd = open(path, "rb")
		try:
			lines = fd.read().decode("utf-8", "replace").splitlines()
		finally:
			fd.close()
		for number, line in enumerate(lines, 1):
			scrubbed = strip_comments_and_strings(line)
			for pattern, label in PY3_ONLY_PATTERNS:
				if pattern.search(scrubbed):
					failures.append("%s:%d: %s -> %s" % (relative, number, label, line.strip()))
	return failures


def main():
	count, compileFailures = check_compile()
	print("byte-compiled %d files with %s" % (count, sys.version.split()[0]))

	py2Failures = check_py2_syntax()

	ok = True
	if compileFailures:
		ok = False
		print("\nCOMPILE ERRORS:")
		for failure in compileFailures:
			print("  " + failure)

	if py2Failures:
		ok = False
		print("\nPY3-ONLY SYNTAX IN PY2-GUARDED FILES:")
		for failure in py2Failures:
			print("  " + failure)

	if ok:
		print("all checks passed")
		return 0
	return 1


if __name__ == "__main__":
	sys.exit(main())
