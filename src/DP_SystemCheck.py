# -*- coding: utf-8 -*-
"""
DreamPlex Plugin by DonDavici, 2012
and jbleyel 2021

Original -> https://github.com/oe-alliance/DreamPlex
Fork -> https://github.com/oe-alliance/DreamPlex

Some of the code is from other plugins:
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
from Components.MenuList import MenuList
from Components.Label import Label

from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from .__common__ import printl2 as printl, revokeCacheFiles

from . import _  # _ is translation

#===============================================================================
#
#===============================================================================


class DPS_SystemCheck(Screen):

	archVersion = None
	check = None
	latestVersion = None

	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)

		self["actions"] = ActionMap(["ColorActions", "SetupActions"],
		{
		"ok": self.startSelection,
		"cancel": self.cancel,
		"red": self.cancel,
		}, -1)

		vlist = []
		vlist.append((_("Revoke cache files manually"), "revoke_cache"))

		self["header"] = Label()
		self["content"] = MenuList(vlist)

		self.onLayoutFinish.append(self.finishLayout)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def finishLayout(self):
		printl("", self, "S")

		self.setTitle(_("System - Systemcheck"))

		self["header"].setText(_("Functions List:"))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def startSelection(self):
		printl("", self, "S")

		selection = self["content"].getCurrent()

		# set package name for object
		content = selection[1]

		if content == "revoke_cache":
			revokeCacheFiles()
			self.session.openWithCallback(self.close, MessageBox, _("Cache files successfully deleted."), MessageBox.TYPE_INFO)

		printl("", self, "C")

	#===================================================================
	#
	#===================================================================

	def cancel(self):
		printl("", self, "S")

		self.close(False, self.session)

		printl("", self, "C")
