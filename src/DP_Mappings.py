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
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER

from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.Label import Label

from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from . import AbstractServerSettings, ServerSettings, ServerSettingsData
from .DP_SettingsStorage import AbstractMappingSettings

from .__common__ import printl2 as printl
from . import _  # _ is translation

from .DP_PathSelector import DPS_PathSelector
from .DP_ViewFactory import getGuiElements

#===============================================================================
# import cProfile
#===============================================================================
try:
	# Python 2.5
	import xml.etree.cElementTree as etree
#printl2("running with cElementTree on Python 2.5+", __name__, "D")
except ImportError:
	try:
		# Python 2.5
		import xml.etree.ElementTree as etree
	#printl2("running with ElementTree on Python 2.5+", __name__, "D")
	except ImportError:
		etree = None
		raise Exception
	#printl2("something weng wrong during xml parsing" + str(e), self, "E")


#===============================================================================
#
#===============================================================================
class DPS_Mappings(Screen):

	remotePath = None
	localPath = None

	def __init__(self, session, server: AbstractServerSettings):
		printl("", self, "S")

		Screen.__init__(self, session)
		self["actions"] = ActionMap(["ColorActions", "SetupActions"],
									{
										"cancel": self.cancel,
										"red": self.redKey,
										"green": self.greenKey,
									}, -1)

		self.guiElements = getGuiElements()
		self.serverpaths = server.listSupportedServerMappings(self.session)
		self.choice = None

		if server.supportServerMapping():
			self["content"] = DPS_MappingsEntryList([], session, server)
			self.updateList()
			self.error = False
		else:
			self.error = True

		self["Title"] = Label(_("Mappings"))

		self["btn_red"] = Pixmap()
		self["btn_redText"] = Label()

		self["btn_green"] = Pixmap()
		self["btn_greenText"] = Label()

		self.onShown.append(self.finishLayout)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def finishLayout(self):
		printl("", self, "S")

		self["btn_red"].instance.setPixmapFromFile(self.guiElements["key_red"])
		self["btn_redText"].setText(_("Delete Entry"))

		self["btn_green"].instance.setPixmapFromFile(self.guiElements["key_green"])
		self["btn_greenText"].setText(_("Add Entry"))

		if self.error:
			self.session.open(MessageBox, _("Something went wrong while opening mappings xml!"), MessageBox.TYPE_INFO)
			self.close()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def updateList(self):
		printl("", self, "S")

		self["content"].buildList()

		printl("", self, "C")

	#===================================================================
	#
	#===================================================================
	def cancel(self):
		printl("", self, "S")

		self.close(False, self.session)

		printl("", self, "C")

	#===================================================================
	#
	#===================================================================
	def greenKey(self):
		printl("", self, "S")

		self.choice = None
		indexCount = 0
		functionList = []
		for serverpaths in self.serverpaths:
			functionList.append((serverpaths, serverpaths, indexCount, ))
			indexCount += 1

		self.session.openWithCallback(self.setSelectedRemotePath, ChoiceBox, title=_("Select server folder"), list=functionList)
		#        self.session.openWithCallback(self.setLocalPathCallback, DPS_PathSelector, "/", "mapping")

		printl("", self, "C")

	#===================================================================
	#
	#===================================================================

	def setSelectedRemotePath(self, choice=None):
		printl("", self, "S")

		if choice:
			self.choice = choice[1]
		self.session.openWithCallback(self.setLocalPathCallback, DPS_PathSelector, "/", "mapping")

		printl("", self, "C")

	#===================================================================
	#
	#===================================================================

	def setLocalPathCallback(self, callback=None, myType=None):
		printl("", self, "S")
		printl("myType: " + str(myType), self, "S")
		printl("choice: " + str(self.choice), self, "S")

		if callback is not None and len(callback):
			printl("localPath: " + str(callback), self, "D")
			self.localPath = str(callback)
			if self.choice:
				self.setRemotePathCallback(self.choice)
			else:
				self.session.openWithCallback(self.setRemotePathCallback, VirtualKeyBoard, title=(_("Enter your remote path segment here:")), text="C:\\Videos or /volume1/videos or \\\\SERVER\\Videos\\")
		else:
			self.session.open(MessageBox, _("Adding new mapping was not completed"), MessageBox.TYPE_INFO)
			self.close()

	#===================================================================
	#
	#===================================================================
	def setRemotePathCallback(self, callback=None):
		printl("", self, "S")

		if callback is not None and len(callback):
			printl("remotePath: " + str(callback), self, "D")
			self.remotePath = str(callback)

			self["content"].addNewMapping(self.remotePath, self.localPath)
		else:
			self.session.open(MessageBox, _("Adding new mapping was not completed"), MessageBox.TYPE_INFO)

		self.close()
		printl("", self, "C")

	#===================================================================
	#
	#===================================================================
	def redKey(self):
		printl("", self, "S")

		content = self["content"].getCurrent()
		if content is not None:
			currentId = content[1][7]
			printl("currentId: " + str(currentId), self, "D")

			self["content"].deleteSelectedMapping(currentId)
		self.close()

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPS_MappingsEntryList(MenuList):

	lastMappingId = 0  # we use this to find the next id if we add a new element

	def __init__(self, menuList, session, server: AbstractServerSettings,enableWrapAround=True):
		printl("", self, "S")
		self.server = server
		self.session = session
		MenuList.__init__(self, menuList, enableWrapAround, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", 20))
		self.l.setFont(1, gFont("Regular", 18))

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def postWidgetCreate(self, instance):
		printl("", self, "S")

		MenuList.postWidgetCreate(self, instance)
		instance.setItemHeight(20)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def buildList(self):
		printl("", self, "S")

		self.list = []

		printl("serverID: " + str(self.server.getIndex()), self, "D")
		printl("servername: " + str(self.server.getName()), self, "D")

		for mapping in self.server.listMappings():
			self.lastMappingId = mapping.id.getValue() if mapping.id.getValue() > self.lastMappingId else self.lastMappingId
			remotePathPart = mapping.remotePath.getValue()
			localPathPart = mapping.localPath.getValue()
			printl("self.lastMappingId: " + str(self.lastMappingId), self, "D")
			printl("remotePathPart: " + str(remotePathPart), self, "D")
			printl("localPathPart: " + str(localPathPart), self, "D")

			el: etree.Element = etree.Element("mapping")
			el.set("id", str(mapping.id.getValue()))
			el.set("remotePathPart", str(mapping.remotePath.getValue()))
			el.set("localPathPart", str(mapping.localPath.getValue()))

			res = [el,
				   (eListboxPythonMultiContent.TYPE_TEXT, 5, 0, 200, 20, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, str(self.lastMappingId)),
				   (eListboxPythonMultiContent.TYPE_TEXT, 50, 0, 300, 20, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, str(localPathPart)),
				   (eListboxPythonMultiContent.TYPE_TEXT, 355, 0, 300, 20, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, str(remotePathPart))]
			self.list.append(res)

		self.l.setList(self.list)
		self.moveToIndex(0)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def deleteSelectedMapping(self, mappingId: str):
		printl("", self, "S")
		printl("serverID: " + str(self.server.getIndex()), self, "D")
		printl("servername: " + str(self.server.getName()), self, "D")
		for mapping in self.server.listMappings():
			printl("mapping: " + str(mapping.id.getValue()), self, "D")
			if mapping.id.getValue() == mappingId:
				self.server.listMappings().remove(mapping)
				self.server.saveChanges()
		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def addNewMapping(self, remotePath, localPath):
		printl("", self, "S")

		newId = int(self.lastMappingId) + 1

		printl("newId: " + str(newId), self, "D")
		printl("remotePath: " + str(remotePath), self, "D")
		printl("localPath: " + str(localPath), self, "D")

		s: ServerSettingsData = ServerSettings[self.server.getType()]
		map: AbstractMappingSettings | None = None
		if s:
			map = s.factoryClass().createNewMapping(str(newId), remotePath, localPath, )
			self.server.listMappings().append(map)
			self.server.saveChanges()
		else: # this server has no node in the xml
			self.session.open(MessageBox, (_("Error:") + "\n%s \n" + _("unsupported mapping:")) % (_("Unsupported mapping for this server")), MessageBox.TYPE_ERROR)

		printl("", self, "C")