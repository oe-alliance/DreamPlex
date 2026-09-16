# -*- coding: utf-8 -*-
"""
Migration of the configuration from the layout used up to version 3.0.

Until 3.0 the configuration lived in three different places:

- global settings and server entries in the enigma2 configuration file,
  /etc/enigma2/settings, as flat "config.plugins.dreamplex.*" keys, with the
  servers as "config.plugins.dreamplex.Entries.<n>.<field>";
- the Home User PINs and tokens in an XML file named "homeUsers";
- the path mappings for direct local playback in an XML file named
  "mountMappings".

Both XML files share the same shape, a <server id="..."> element per server
holding one child per entry.

From 3.1 everything lives in a single XML store. This module reads the old
layout, when present, and produces the new document, so that an upgrade keeps
servers, users, PINs, tokens and mappings instead of starting from scratch.

The field names line up almost exactly: 40 of the 44 server fields keep the
same name. The four that do not - nasRoot, nasOverrideIp, smbUser,
smbPassword - belong to the SMB/UNC "direct remote" playback, which never
worked: in the released code the assignment that would enable it is commented
out, so the branch reading those values is unreachable. They are copied into
the new document anyway, as inert data, so that nothing the user typed is
thrown away.
"""
from __future__ import annotations

import os
from xml.etree.ElementTree import Element, SubElement, ElementTree

from .__common__ import printl2 as printl, getXmlContent

LEGACY_PREFIX = "config.plugins.dreamplex."
LEGACY_ENTRIES = LEGACY_PREFIX + "Entries."

ENIGMA2_SETTINGS = "/etc/enigma2/settings"

# Global settings whose name changed between the two layouts.
GLOBAL_RENAMES = {
	"configfolderpath": "configFolderPath",
	"cachefolderpath": "cacheFolderPath",
	"logfolderpath": "logFolderPath",
	"mediafolderpath": "mediaFolderPath",
	"pluginfolderpath": "pluginFolderPath",
	"skinfolderpath": "skinFolderPath",
	"lcd": "lcd4linux",
	"entriescount": None,   # implicit in the new layout, dropped
	"Entries": None,        # handled separately
}

# Server fields that no longer have a counterpart. Preserved verbatim.
ORPHAN_SERVER_FIELDS = ("nasRoot", "nasOverrideIp", "smbUser", "smbPassword")

SERVER_ELEMENT = "server-settings"
SERVER_TYPE_ATTRIBUTE = "server-type"

# Only Plex existed before 3.1, so every migrated server is a Plex one.
LEGACY_SERVER_TYPE = "PlexServer"


#===============================================================================
#
#===============================================================================
def readEnigma2Settings(path=ENIGMA2_SETTINGS) -> dict:
	"""Read the "config.plugins.dreamplex.*" keys from the enigma2 settings.

	Returns a dict without the prefix. An absent or unreadable file simply
	yields an empty dict: there is nothing to migrate then.
	"""
	values = {}

	if not os.path.isfile(path):
		printl("no enigma2 settings at " + str(path), "DPH_ConfigMigration", "D")
		return values

	try:
		with open(path, "r") as fh:
			for line in fh:
				line = line.strip()
				if not line.startswith(LEGACY_PREFIX) or "=" not in line:
					continue
				key, _sep, value = line.partition("=")
				values[key.strip()[len(LEGACY_PREFIX):]] = value.strip()
	except Exception as ex:
		printl("cannot read enigma2 settings: " + str(ex), "DPH_ConfigMigration", "W")

	return values


#===============================================================================
#
#===============================================================================
def _legacyXmlEntries(location: str, childTag: str) -> dict:
	"""Read one of the old XML files into {serverId: [attribute dicts]}.

	Both files use the same shape:

	    <xml><server id="0"><user id=".." username=".."/></server></xml>
	"""
	result = {}

	if not location or not os.path.isfile(location):
		return result

	tree = getXmlContent(location)
	if tree is None:
		printl("cannot parse " + str(location), "DPH_ConfigMigration", "W")
		return result

	try:
		for server in tree.findall("server"):
			serverId = str(server.get("id"))
			children = [dict(child.attrib) for child in server.findall(childTag)]
			if children:
				result.setdefault(serverId, []).extend(children)
	except Exception as ex:
		printl("cannot read " + str(location) + ": " + str(ex), "DPH_ConfigMigration", "W")

	return result


#===============================================================================
#
#===============================================================================
def findLegacyXml(configFolder: str, name: str) -> str | None:
	"""Locate one of the old XML files.

	Their position varied between versions, so several plausible places are
	tried rather than assuming one.
	"""
	candidates = [
		os.path.join(configFolder, name),
		os.path.join(configFolder, name, name + ".xml"),
		os.path.join(configFolder, name, "users.xml"),
		os.path.join("/hdd/dreamplex", name),
		os.path.join("/hdd/dreamplex", name, "users.xml"),
		os.path.join("/hdd/dreamplex", name, name + ".xml"),
	]

	for candidate in candidates:
		if os.path.isfile(candidate):
			printl("found legacy " + name + " at " + candidate, "DPH_ConfigMigration", "I")
			return candidate

	return None


#===============================================================================
#
#===============================================================================
def _groupServerEntries(legacy: dict) -> dict:
	"""Group the flat "Entries.<n>.<field>" keys by server index."""
	servers = {}

	for key, value in legacy.items():
		if not key.startswith("Entries."):
			continue
		rest = key[len("Entries."):]
		index, _sep, field = rest.partition(".")
		if not field:
			continue
		servers.setdefault(index, {})[field] = value

	return servers


#===============================================================================
#
#===============================================================================
def buildSettingsTree(legacy: dict, users: dict, mappings: dict) -> Element:
	"""Build the new document from the three old sources."""
	root = Element("dreamplex")

	# --- global settings ---
	for key, value in sorted(legacy.items()):
		if key.startswith("Entries."):
			continue
		name = GLOBAL_RENAMES.get(key, key)
		if name is None:
			continue
		SubElement(root, name).text = value

	# --- servers ---
	for index, fields in sorted(_groupServerEntries(legacy).items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
		server = SubElement(root, SERVER_ELEMENT, {SERVER_TYPE_ATTRIBUTE: LEGACY_SERVER_TYPE})

		if "id" not in fields:
			fields["id"] = index

		for field, value in sorted(fields.items()):
			SubElement(server, field).text = value

		# users belonging to this server
		for user in users.get(str(index), []):
			element = SubElement(server, "user")
			for attribute, value in sorted(user.items()):
				SubElement(element, attribute).text = value

		# path mappings belonging to this server
		for mapping in mappings.get(str(index), []):
			element = SubElement(server, "mapping")
			# the old names carried a "Part" suffix
			renamed = {
				"remotePathPart": "remotePath",
				"localPathPart": "localPath",
			}
			for attribute, value in sorted(mapping.items()):
				SubElement(element, renamed.get(attribute, attribute)).text = value

	return root


#===============================================================================
#
#===============================================================================
def _clearLegacySettings(path: str) -> None:
	"""Strip the "config.plugins.dreamplex.*" lines from the enigma2 settings.

	/etc/enigma2/settings is shared by every plugin and setting on the box,
	so only our own keys are removed - the rest of the file is left exactly
	as it was. Called once migration has actually written the new document,
	so that a later run never finds legacy data to migrate again (readEnigma2
	Settings() returning an empty dict is what makes migrate() a no-op).
	"""
	try:
		with open(path, "r") as fh:
			lines = fh.readlines()
	except Exception as ex:
		printl("cannot read " + str(path) + " for cleanup: " + str(ex), "DPH_ConfigMigration", "W")
		return

	kept = [line for line in lines if not line.strip().startswith(LEGACY_PREFIX)]
	removed = len(lines) - len(kept)
	if removed == 0:
		return

	try:
		with open(path, "w") as fh:
			fh.writelines(kept)
		printl("removed %d legacy dreamplex line(s) from %s" % (removed, path), "DPH_ConfigMigration", "I")
	except Exception as ex:
		printl("cannot write " + str(path) + " for cleanup: " + str(ex), "DPH_ConfigMigration", "W")
		return

	# enigma2 loaded this file into its own in-memory config tree well before
	# our plugin ever runs, and periodically rewrites the whole file from
	# that memory (any settings change, standby, a clean shutdown...). Without
	# forcing a reload here, its in-memory copy still has the lines we just
	# removed, and the next such write brings them straight back - silently
	# undoing this cleanup and leaving the file ready to trigger a re-migration
	# again later.
	try:
		from Components.config import configfile
		configfile.load()
	except Exception as ex:
		printl("cannot reload enigma2 settings after cleanup: " + str(ex), "DPH_ConfigMigration", "W")


#===============================================================================
#
#===============================================================================
def migrate(location: str, configFolder: str, enigma2Settings: str = ENIGMA2_SETTINGS) -> bool:
	"""Write the new settings file from the old configuration.

	Returns True if something was actually migrated. The caller is expected to
	have checked that "location" does not exist yet.
	"""
	printl("", "DPH_ConfigMigration", "S")

	legacy = readEnigma2Settings(enigma2Settings)
	if not legacy:
		printl("nothing to migrate", "DPH_ConfigMigration", "I")
		printl("", "DPH_ConfigMigration", "C")
		return False

	usersFile = findLegacyXml(configFolder, "homeUsers")
	mappingsFile = findLegacyXml(configFolder, "mountMappings")

	users = _legacyXmlEntries(usersFile, "user") if usersFile else {}
	mappings = _legacyXmlEntries(mappingsFile, "mapping") if mappingsFile else {}

	root = buildSettingsTree(legacy, users, mappings)

	serverCount = len(root.findall(SERVER_ELEMENT))
	printl("migrated settings: %d, servers: %d, users: %d, mappings: %d"
		   % (len(legacy), serverCount,
			  sum(len(v) for v in users.values()),
			  sum(len(v) for v in mappings.values())),
		   "DPH_ConfigMigration", "I")

	try:
		ElementTree(root).write(location, encoding="utf-8", xml_declaration=True)
	except Exception as ex:
		printl("cannot write " + str(location) + ": " + str(ex), "DPH_ConfigMigration", "W")
		printl("", "DPH_ConfigMigration", "C")
		return False

	# Without this, "config.plugins.dreamplex.*" stays in the enigma2
	# settings forever, and readEnigma2Settings() finds it again on any
	# future run where, for whatever reason, this function gets called even
	# though settings.xml already exists - overwriting it with the stale
	# pre-3.1 data. Only clear it once the new document has actually been
	# written successfully.
	_clearLegacySettings(enigma2Settings)

	printl("", "DPH_ConfigMigration", "C")
	return True
