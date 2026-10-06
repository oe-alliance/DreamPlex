# -*- coding: utf-8 -*-
"""The playback type has to be set before the media options are asked for.

DP_Player.playMedia() asks the library for the media options in a worker
(getMediaOptionsToPlay) and, until now, set the playback type only later,
once a version was chosen (setPlaybackType, in setSelectedMedia). But
getMediaOptionsToPlay() already reads that type: its first step,
getTranscodeSettings(), builds the client capabilities only when the type in
force says "transcode". Set afterwards, that read saw the PREVIOUS playback's
type - with a server configured as streamed, the first transcoded play sent
X-Plex-Client-Capabilities empty. And anything that made the order of the
versions depend on the type would sort them by the previous play as well.

Spotted by the DreamFin fork, which shares DP_Player and moved the call the
same way. This guard keeps setPlaybackType() ahead of every
getMediaOptionsToPlay() call in the player, in the same function.

Left out on purpose: DP_View.onKeyVideo() also asks for media options (the
extras) and sets no playback type at all; that path is a separate question,
not this ordering.
"""

import ast
import os
import unittest

PLAYER = os.path.join(
	os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "DP_Player.py")

ASK = "getMediaOptionsToPlay"
SET = "setPlaybackType"

# getMediaOptionsToPlay call sites in the player when this guard was written;
# if the scan ever finds fewer, it is the scan that broke, not the code
KNOWN_CALL_SITES = 1


def _own_calls(func, name):
	"""Calls to <anything>.name(...) made by func itself, not by functions
	nested in it, in source order."""
	found = []
	pending = list(ast.iter_child_nodes(func))
	while pending:
		node = pending.pop()
		if isinstance(node, (ast.FunctionDef, ast.Lambda, ast.ClassDef)):
			continue
		if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
				and node.func.attr == name):
			found.append(node)
		pending.extend(ast.iter_child_nodes(node))
	return sorted(found, key=lambda call: (call.lineno, call.col_offset))


def _is_players_own_type(call):
	"""True for setPlaybackType(str(self.playbackMode))."""
	if len(call.args) != 1:
		return False
	arg = call.args[0]
	return (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
		and arg.func.id == "str" and len(arg.args) == 1
		and isinstance(arg.args[0], ast.Attribute) and arg.args[0].attr == "playbackMode"
		and isinstance(arg.args[0].value, ast.Name) and arg.args[0].value.id == "self")


class TestPlaybackTypeComesFirst(unittest.TestCase):
	def setUp(self):
		with open(PLAYER) as handle:
			self.tree = ast.parse(handle.read())

	def _functions(self):
		for node in ast.walk(self.tree):
			if isinstance(node, ast.FunctionDef):
				yield node

	def test_the_type_is_set_before_the_options_are_asked_for(self):
		examined = 0
		problems = []

		for func in self._functions():
			asks = _own_calls(func, ASK)
			if not asks:
				continue
			sets = _own_calls(func, SET)
			for ask in asks:
				examined += 1
				earlier = [s for s in sets if (s.lineno, s.col_offset) < (ask.lineno, ask.col_offset)]
				if not earlier:
					problems.append("%s (line %d) asks for the media options without setting the "
						"playback type first" % (func.name, ask.lineno))
				elif not _is_players_own_type(earlier[-1]):
					problems.append("%s (line %d) sets a playback type that is not the player's own "
						"(str(self.playbackMode))" % (func.name, earlier[-1].lineno))

		self.assertGreaterEqual(
			examined, KNOWN_CALL_SITES,
			"only found %d %s call sites, expected at least %d - the scan is broken, not the code"
			% (examined, ASK, KNOWN_CALL_SITES))

		self.assertEqual(
			problems, [],
			"getMediaOptionsToPlay() reads the playback type, so it must be set before: %s "
			"(checked %d call sites)" % ("; ".join(problems), examined))


if __name__ == "__main__":
	unittest.main()
