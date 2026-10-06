# -*- coding: utf-8 -*-
"""AUDIO during playback must not lean on a method of the image.

InfobarAudioSelectionExtended.audioSelection() opens the audio screen with a
callback for when it closes. It used to pass self.audioSelected, which the
plugin never defined: it came from the image's InfoBarAudioSelection. OpenATV
removed it on 2025-05-05 (d9491ef, "[InfoBarGenerics]") - 6.4 and 7.0-7.5
have it, 7.6, 8.0 and master do not - so on 7.6 and 8.0 the key raised
AttributeError before the screen even opened, and took the player down.

DP_Player cannot be imported here (it pulls in InfoBarGenerics), so the real
class is compiled from the source on top of two stand-ins for the image's
InfoBarAudioSelection: one as up to 7.5, with audioSelected(), and one as
from 7.6, without it. Each presses AUDIO and then closes the screen.
AudioSelection itself always closes with close(0), from OK and from EXIT; a
bare close() is covered as well, as the image's own callbacks accept both.

Found by the DreamFin fork, from a crash log of this plugin on OpenATV 8.0.1.
"""

import ast
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
PLAYER = os.path.join(SRC, "DP_Player.py")

MY_AUDIO_SELECTION = object()  # stands in for the screen class the key opens


def _printl(*args, **kwargs):
	pass


def classModule(path, classname):
	"""A module holding only the real ClassDef, ready to compile."""
	handle = io.open(path, "rb")
	try:
		tree = ast.parse(handle.read(), filename=path)
	finally:
		handle.close()

	found = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == classname]
	assert found, "class %s not found in %s" % (classname, path)
	module = ast.Module(body=[found[0]])
	module.type_ignores = []
	return module


CLASS_MODULE = classModule(PLAYER, "InfobarAudioSelectionExtended")


class ImageUpTo75(object):
	"""The image's InfoBarAudioSelection on OpenATV 6.4 to 7.5."""

	def __init__(self):
		pass

	def audioSelected(self, ret=None):
		pass


class ImageFrom76(object):
	"""The same class on OpenATV 7.6, 8.0 and master: audioSelected() is gone."""

	def __init__(self):
		pass


class Session(object):
	infobar = None

	def __init__(self):
		self.opened = []

	def openWithCallback(self, callback, screen, *args, **kwargs):
		self.opened.append((callback, screen, kwargs))


def buildPlayer(imageBase):
	"""An instance of the real InfobarAudioSelectionExtended over imageBase."""
	namespace = {"InfoBarAudioSelection": imageBase, "printl": _printl,
			"myAudioSelection": MY_AUDIO_SELECTION}
	exec(compile(CLASS_MODULE, PLAYER, "exec"), namespace)
	player = namespace["InfobarAudioSelectionExtended"]()
	player.session = Session()
	return player


class TestAudioKey(unittest.TestCase):
	def pressAndClose(self, imageBase, *closeArgs):
		player = buildPlayer(imageBase)

		player.audioSelection()  # the AUDIO key

		self.assertEqual(len(player.session.opened), 1, "AUDIO must open exactly one screen")
		callback, screen, kwargs = player.session.opened[0]
		self.assertIs(screen, MY_AUDIO_SELECTION)
		self.assertIs(kwargs.get("infobar"), player)
		callback(*closeArgs)  # the screen closes

	def test_up_to_75_closed_with_a_result(self):
		self.pressAndClose(ImageUpTo75, 0)

	def test_up_to_75_closed_without_a_result(self):
		self.pressAndClose(ImageUpTo75)

	def test_from_76_closed_with_a_result(self):
		self.pressAndClose(ImageFrom76, 0)

	def test_from_76_closed_without_a_result(self):
		self.pressAndClose(ImageFrom76)

	def test_the_callback_is_the_plugins_own(self):
		# where the image still has audioSelected() the old code worked, and
		# that is exactly how it went unnoticed until the image dropped it
		player = buildPlayer(ImageUpTo75)
		player.audioSelection()

		callback = player.session.opened[0][0]
		self.assertIn(callback.__name__, vars(type(player)),
				"the callback %s() is inherited from the image, which can drop it "
				"in any release" % callback.__name__)


if __name__ == "__main__":
	unittest.main()
