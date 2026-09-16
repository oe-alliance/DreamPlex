# -*- coding: utf-8 -*-
"""
Presence of this file is what makes DreamPlex's ServiceLoader-style scan
(_discoverServerBackends() in src/__init__.py) treat "jellyfin" as a server
backend to import - importing it is the self-registration step itself.
"""
from .JellyfinSettings import JellyfinSettings, JellyfinSettingsFactory
from .. import registerServerBackend


def _jellyfinLogSanitizer(string: str, steps: list, obfuscate: bool) -> str:
	# Jellyfin 12.0 removed X-Emby-Authorization/X-MediaBrowser-Token/
	# X-Emby-Token entirely (see JellyfinSettings.buildAuthorizationHeaderValue)
	# in favor of a single combined "Authorization: MediaBrowser ..." header -
	# both the DeviceId and the Token parameters inside it need the same
	# redaction the two separate legacy headers used to get.
	offset = string.find("Authorization")
	if not offset == -1:
		device_id_offset = string.find("DeviceId=", offset)
		if not device_id_offset == -1:
			steps[0] = 8
			start = device_id_offset + 10
			end = string.find('"', start)
			if end != -1:
				string = string[0:start] + "********" + string[end-8:]

		token_offset = string.find("Token=", offset)
		if not token_offset == -1:
			steps[0] = 8
			start = token_offset + 7
			end = string.find('"', start)
			if end != -1:
				string = string[0:start] + "********" + string[end-8:]

	# Legacy header names, kept in case an old log line or a third-party
	# component (e.g. the remote-control protocol, see getRemote*() in
	# JellyfinLibrary.py, unrelated to server auth) still emits them.
	offset = string.find("X-MediaBrowser-Token")
	if not offset == -1:
		steps[0] = 8
		start = offset + 20
		end = start + steps[0]
		new_string = string[0:start] + "********" + string[end:]
		string = new_string

	return string


registerServerBackend(JellyfinSettings, JellyfinSettingsFactory, logSanitizer=_jellyfinLogSanitizer)
