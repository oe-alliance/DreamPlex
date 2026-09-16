# -*- coding: utf-8 -*-
"""
Trust checks for cache files serialized with pickle.

The pickle format is not a data format but a program: pickle.load()
reconstructs the objects by executing the instructions contained in the file,
so loading a tampered .cache file amounts to running arbitrary code with the
privileges of enigma2, that is root.

The realistic vector is not an attacker who already has access to the box, but
the /hdd directory shared over the network: on these machines it is common
practice to export it over Samba or NFS, and in that case anybody on the LAN
can drop a file into the cache directory.

The functions below do not make pickle safe - nothing makes it safe on
untrusted input - but they verify that the file about to be loaded was written
by us and is not writable by anybody else.
"""
from __future__ import annotations

import os
import stat

from .__common__ import printl2 as printl

# Permissions used when creating cache files: read and write for the owner
# only.
CACHE_FILE_MODE = 0o600


def isCacheFileTrusted(path: str) -> bool:
	"""True if the cache file can be deserialized safely.

	Rejects symbolic links (which could point elsewhere), anything that is not
	a regular file, files owned by another user, and files writable by group
	or others.
	"""
	try:
		info = os.lstat(path)
	except OSError as ex:
		printl("cannot stat cache file: " + str(ex), "DPH_CacheGuard", "D")
		return False

	if stat.S_ISLNK(info.st_mode):
		printl("refusing cache file: is a symlink: " + str(path), "DPH_CacheGuard", "W")
		return False

	if not stat.S_ISREG(info.st_mode):
		printl("refusing cache file: not a regular file: " + str(path), "DPH_CacheGuard", "W")
		return False

	if info.st_uid != os.getuid():
		printl("refusing cache file: owned by uid " + str(info.st_uid) + ": " + str(path), "DPH_CacheGuard", "W")
		return False

	if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
		printl("refusing cache file: writable by group or others: " + str(path), "DPH_CacheGuard", "W")
		return False

	return True


def secureCacheFile(path: str) -> None:
	"""Restrict the permissions of a cache file that has just been written."""
	try:
		os.chmod(path, CACHE_FILE_MODE)
	except OSError as ex:
		printl("cannot chmod cache file: " + str(ex), "DPH_CacheGuard", "D")
