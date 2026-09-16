# -*- coding: utf-8 -*-
"""
DreamPlex Plugin by DonDavici, 2012
and jbleyel 2021

Original -> https://github.com/oe-alliance/DreamPlex
Fork -> https://github.com/oe-alliance/DreamPlex

Some code is from other plugins:
all credits to the coders :-)

DreamPlex Plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 2 of the License, or
(at your option) any later version.

DreamPlex Plugin is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
"""
#=================================
#IMPORT
#=================================
from Components.ActionMap import ActionMap
from Screens.InputBox import InputBox
from Screens.Screen import Screen

from .DPH_ScreenHelper import DPH_ScreenHelper

from .__common__ import printl2 as printl
from . import _  # _ is translation

#===============================================================================
#
#===============================================================================


class DPS_DeleteKeysMixin(object):
	"""Adds Yellow/Green as delete-left/delete-right to an InputBox subclass.

	The stock InputBox only wires character deletion to the "deleteForward"/
	"deleteBackward" named actions, which some universal remotes never send
	(they only reproduce the handful of raw codes behind color/OK/arrow
	keys), making it impossible to correct a typo. Red was the first choice,
	but on-device logs showed "Keymap 'ColorActions' -> Action = 'red'."
	immediately followed by the dialog closing, with neither of this
	mixin's own log lines ever printing - the base InputBox itself already
	binds Red as an accessibility shortcut for cancel (a convention used
	throughout enigma2), and it wins over this mixin's ActionMap. Yellow and
	Green are unused by the base InputBox, so they are repurposed here for
	backward/forward delete. Call _wireDeleteKeys() after InputBox.__init__()
	has run (it needs self["input"] to already exist).
	"""

	def _wireDeleteKeys(self):
		self["DPS_DeleteKeysActions"] = ActionMap(["ColorActions"],
			{
				"yellow": self._deleteBackward,
				"green": self._deleteForward,
			}, -1)

	def _deleteBackward(self):
		printl("yellow pressed, before: " + repr(self["input"].getText()), self, "D")
		fn = getattr(self, "keyBackspace", None)
		if callable(fn):
			fn()
		else:
			inp = self["input"]
			if hasattr(inp, "deleteBackward"):
				inp.deleteBackward()
		printl("yellow pressed, after: " + repr(self["input"].getText()), self, "D")

	def _deleteForward(self):
		printl("green pressed, before: " + repr(self["input"].getText()), self, "D")
		fn = getattr(self, "keyDelete", None)
		if callable(fn):
			fn()
		else:
			inp = self["input"]
			if hasattr(inp, "delete"):
				inp.delete()
		printl("green pressed, after: " + repr(self["input"].getText()), self, "D")

#===============================================================================
#
#===============================================================================


class DPS_TextInputBox(DPS_DeleteKeysMixin, InputBox):
	"""Plain InputBox with the Yellow/Green delete keys wired up.

	Two earlier attempts both failed on-device: neither the system's own
	"InputBox" skin nor a ["DPS_TextInputBox", "InputBox"] fallback list
	resolved at all ("No skin to read or screen to display", a fully
	invisible 0-size layout); reusing "DPS_InputBox" (the search box's skin)
	resolved but dragged in its mini-tv live-preview widget, which is
	meaningless here and visually took over the screen. There is now a
	dedicated "DPS_TextInputBox" block in every skin.xml - the same
	"text"/"input" widgets, centered, no mini-tv - so this finally has a
	skin of its own instead of borrowing one built for a different purpose.
	There is no button-legend widget to label Yellow/Green with, so the
	hint is appended to the title instead.
	"""

	skinName = "DPS_TextInputBox"

	def __init__(self, session, title="", **kwargs):
		title = title + "\n" + _("(YELLOW = delete left, GREEN = delete right)")
		InputBox.__init__(self, session, title=title, **kwargs)
		self._wireDeleteKeys()

#===============================================================================
#
#===============================================================================


class DPS_InputBox(DPS_DeleteKeysMixin, InputBox, DPH_ScreenHelper):

	#===========================================================================
	#
	#===========================================================================
	def __init__(self, session, *args, **kwargs):
		Screen.__init__(self, session)
		InputBox.__init__(self, session, **kwargs)
		DPH_ScreenHelper.__init__(self)
		self._wireDeleteKeys()
		self.entryData = args

		self.initScreen("input_box")

		printl("entryData: " + str(self.entryData), self, "D")

		self.setTitle(_("Search ..."))

		self.onLayoutFinish.append(self.finishLayout)

	#===============================================================================
	#
	#===============================================================================
	def finishLayout(self):
		printl("", self, "S")

		self.initMiniTv()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def go(self):
		printl("", self, "S")

		self.close(self.entryData, self["input"].getText())

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def cancel(self):
		printl("", self, "S")

		self.close(self.entryData)

		printl("", self, "C")
