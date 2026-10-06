# -*- coding: utf-8 -*-
"""Stub of enigma2's Tools.Directories."""

import os
import shutil
import tempfile

SCOPE_PLUGINS = "SCOPE_PLUGINS"
SCOPE_SKIN = "SCOPE_SKIN"
SCOPE_CURRENT_SKIN = "SCOPE_CURRENT_SKIN"
SCOPE_LANGUAGE = "SCOPE_LANGUAGE"

_BASE = os.path.join(tempfile.gettempdir(), "dreamplex-test-scopes")


def resolveFilename(scope, base=""):
	# keep any trailing slash the caller provided (DreamPlex relies on it)
	resolved = os.path.join(_BASE, str(scope), base.replace("/", os.sep))
	if base.endswith("/") and not resolved.endswith(("/", os.sep)):
		resolved += "/"
	return resolved


def fileExists(f, mode="r"):
	return os.path.exists(f)


def copyfile(src, dst):
	shutil.copyfile(src, dst)


def pathExists(path):
	return os.path.exists(path)
