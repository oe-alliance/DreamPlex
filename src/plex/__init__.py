# -*- coding: utf-8 -*-
"""
Presence of this file is what makes DreamPlex's ServiceLoader-style scan
(_discoverServerBackends() in src/__init__.py) treat "plex" as a server
backend to import - importing it is the self-registration step itself.
"""
from .PlexSettings import PlexSettings, PlexSettingsFactory
from .. import registerServerBackend


def _plexLogSanitizer(string: str, steps: list, obfuscate: bool) -> str:
	offset = string.find("X-Plex-Token")
	if not string.find("X-Plex-Token") == -1:
		steps[0] = 8
		start = offset + 13
		end = start + steps[0]
		new_string = string[0:start] + "********" + string[end:]
		string = new_string

	return string


registerServerBackend(PlexSettings, PlexSettingsFactory, logSanitizer=_plexLogSanitizer)
