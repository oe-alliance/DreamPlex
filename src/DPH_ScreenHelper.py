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
#===============================================================================
# IMPORT
#===============================================================================
from enigma import eSize, getDesktop

from Components.config import config
from Components.ActionMap import HelpableActionMap
from Components.VideoWindow import VideoWindow
from Components.Label import Label
from Components.Label import MultiColorLabel
from Components.config import NumericalTextInput

from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen

from skin import parseColor
from six import PY2

from .DPH_Singleton import Singleton
from .DP_ViewFactory import translateValues

from .__common__ import printl2 as printl, addNewScreen, closePlugin, getSkinResolution, getSkinHighlightedColor, getSkinNormalColor
from . import _  # _ is translation

#===============================================================================
#
#===============================================================================


class DPH_ScreenHelper(object):
	width = "195"
	height = "268"
	#===============================================================================
	#
	#===============================================================================

	def __init__(self, forceMiniTv=False):
		printl("", self, "S")

		self.stopLiveTvOnStartup = Singleton().getSettingsInstance().stopLiveTvOnStartup.getValue()

		# we use this e.g in DP_View to use miniTv for backdrops via libiframe
		self.forceMiniTv = forceMiniTv

		if not self.stopLiveTvOnStartup or self.forceMiniTv:
			self["miniTv"] = VideoWindow(decoder=0)
			self.miniTvInUse = True
		else:
			self["miniTv"] = Label()

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def initMiniTv(self, width=None, height=None):
		"""
		the widht and height is in params files a param section on its own
		but for the views the settings located there for this reason
		we have both ways.
		"""
		printl("", self, "S")

		if not self.stopLiveTvOnStartup or self.forceMiniTv:
			if width is None or height is None:
				width, height = self.getMiniTvParams()
			desk = getDesktop(0)
			print(str(self["miniTv"].instance))
			self["miniTv"].instance.setFBSize(desk.size())
			self["miniTv"].instance.resize(eSize(int(width), int(height)))
		else:
			self["miniTv"].hide()

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def getMiniTvParams(self):
		printl("", self, "S")

		width = 400
		height = 225
		printl("screenName: " + str(self.screenName), self, "D")

		if self.height is not None and self.width is not None:
			height = self.height
			width = self.width

		printl("width: " + str(width) + " - height: " + str(height), self, "D")
		printl("", self, "C")
		return int(width), int(height)

	#===============================================================================
	#
	#===============================================================================
	def initScreen(self, screenName):
		printl("", self, "S")

		tree = Singleton().getSkinParamsInstance()

		self.screenName = screenName

		for screen in tree.findall('screen'):
			name = str(screen.get('name'))

			if name == self.screenName:
				self.miniTv = translateValues(str(screen.get('miniTv')))
				if self.miniTv:
					self.width = screen.get('width')
					self.height = screen.get('height')
				else:
					self.Poster = translateValues(str(screen.get('usePoster')))
					if self.Poster:
						self.width = screen.get('width')
						self.height = screen.get('height')

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPH_PlexScreen(object):

	#===============================================================================
	#
	#===============================================================================
	def __init__(self):

		self.skinResolution = getSkinResolution()

	#===============================================================================
	#
	#===============================================================================
	def setColorFunctionIcons(self):
		# first we set the pics for buttons if existing
		try:
			self["btn_red"].instance.setPixmapFromFile(self.guiElements["key_red"])

		except Exception:
			pass

		try:
			self["btn_green"].instance.setPixmapFromFile(self.guiElements["key_green"])
		except Exception:
			pass

		try:
			self["btn_yellow"].instance.setPixmapFromFile(self.guiElements["key_yellow"])
		except Exception:
			pass

		try:
			self["btn_blue"].instance.setPixmapFromFile(self.guiElements["key_blue"])
		except Exception:
			pass

#===============================================================================
#
#===============================================================================


class DPH_MultiColorFunctions(object):

	#===============================================================================
	#
	#===============================================================================
	def __init__(self):
		printl("", self, "S")

		self.colorFunctionContainer = {}
		self.colorFunctionContainer["red"] = {}
		self.colorFunctionContainer["green"] = {}
		self.colorFunctionContainer["yellow"] = {}
		self.colorFunctionContainer["blue"] = {}

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def setColorFunction(self, color, level, functionList):
		#printl("", self, "S")

		self.colorFunctionContainer[color][level] = functionList

		#printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def getColorFunction(self, color, level):
		printl("", self, "S")

		# we put this into try because if there is no function registered it will come a gs
		try:
			return self.colorFunctionContainer[color][level][1]
		except Exception:
			return False

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def alterColorFunctionNames(self, level):
		printl("", self, "S")
		colorList = ["red", "green", "yellow", "blue"]

		for color in colorList:
			functionList = self.colorFunctionContainer[color][level]

			if functionList is not None:
				# Unconditional show(), not gated on getVisible() - DP_View's
				# own refresh() also shows/hides btn_yellow independently
				# (hideRefreshFunction/showRefreshFunction, based on whether
				# the selected row is a real OS folder) whenever the level is
				# "2". getVisible() could still report the pre-hide value for
				# a moment after that runs, before the GUI actually repaints -
				# the old guard then wrongly believed the button was already
				# visible and skipped re-showing it, which is what made the
				# yellow "refresh Library" button randomly seem to vanish
				# while switching levels back and forth on a page with a
				# folder row selected.
				self["btn_" + color + "Text"].show()
				self["btn_" + color].show()
				self["btn_" + color + "Text"].setText(self.colorFunctionContainer[color][level][0])
			else:
				self["btn_" + color + "Text"].hide()
				self["btn_" + color].hide()

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def setMultiLevelElements(self, levels):
		printl("", self, "S")
		self.levels = levels

		dp_highlighted = parseColor(getSkinHighlightedColor())
		dp_normal = parseColor(getSkinNormalColor())

		for i in range(1, int(levels) + 1):
			self["L" + str(i)] = MultiColorLabel()
			self["L" + str(i)].foreColors = [dp_highlighted, dp_normal]
			self["L" + str(i)].setText(str(i))

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def setLevelActive(self, currentLevel):
		printl("", self, "S")

		self.currentFunctionLevel = currentLevel
		printl("currentFunctionLevel: " + str(self.currentFunctionLevel), self, "D")

		for i in range(1, int(self.levels) + 1):
			if int(self.currentFunctionLevel) == int(i):
				self["L" + str(i)].setForegroundColorNum(0)
			else:
				self["L" + str(i)].setForegroundColorNum(1)

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPH_Screen(Screen, HelpableScreen):

	#===============================================================================
	#
	#===============================================================================
	def __init__(self, session):
		printl("", self, "S")

		Screen.__init__(self, session)
		# DPS_MainMenu/DPS_ServerMenu/DP_View (the three screens built on
		# DPH_Screen) already populate self.helpList with real descriptions
		# via their own HelpableActionMap entries (Screen.__init__ always
		# creates that list - see Screens.Screen - so it was never empty),
		# but nothing ever actually opened the Help screen on them: none of
		# the three mixed in HelpableScreen, the class that binds the native
		# HELP key to showHelp(). DP_Player/DPS_Settings already did this
		# themselves; this closes the same gap here, for all three at once.
		HelpableScreen.__init__(self)

		self["globalActions"] = HelpableActionMap(self, "DP_PluginCloser",
			{
			    "stop": (self.closePlugin, _("Close DreamPlex")),
			}, -2)

		# Second trigger for the same Help screen, on LIST - some remotes'
		# native HELP button does not reach the box as KEY_HELP; LIST is a
		# safe pick: unused anywhere in this plugin, and its one native
		# meaning (open the recordings list, "InfobarActions" context) only
		# exists inside the live-TV InfoBar, which is not active while a
		# DreamPlex screen is on screen.
		self["helpShortcut"] = HelpableActionMap(self, "DP_HelpShortcut",
			{
			    "helpAlt": (self.showHelp, _("Show help")),
			}, -2)

		self.onLayoutFinish.append(self.addNewScreen)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def addNewScreen(self):
		printl("", self, "S")

		addNewScreen(self)

		printl("", self, "C")

	#===============================================================================
	#
	#===============================================================================
	def closePlugin(self):
		printl("", self, "S")

		closePlugin(self.session)

		printl("", self, "C")

#===============================================================================
#
#===============================================================================


class DPH_Filter(NumericalTextInput):

	#===============================================================================
	#
	#===============================================================================
	def __init__(self, digitHelp=None):
		printl("", self, "S")

		NumericalTextInput.__init__(self)

		self["number_key_popup"] = Label()
		self["number_key_popup"].hide()

		# digitHelp: optional {key: description} override for the Help
		# legend, e.g. DP_View's "1".."4" (which switch what the color
		# buttons do, not T9 search input there - see its own onKey1..4).
		# Enigma2's HelpableActionMap freezes these descriptions into the
		# screen's helpList at construction time (Screens.HelpMenu reads
		# them from there, not from this map live), so unlike the on-screen
		# color-button labels there is no cheap way to make this text
		# track the *current* level - it can only carry one fixed
		# description per key, chosen to make sense across all of them.
		digitHelp = digitHelp or {}
		self["filterActions"] = HelpableActionMap(self, "DP_FilterMenuActions",
			{
			"1": (self.onKey1, digitHelp.get("1", "")),
			"2": (self.onKey2, digitHelp.get("2", "")),
			"3": (self.onKey3, digitHelp.get("3", "")),
			"4": (self.onKey4, digitHelp.get("4", "")),
			"5": (self.onKey5, digitHelp.get("5", "")),
			"6": (self.onKey6, digitHelp.get("6", "")),
			"7": (self.onKey7, digitHelp.get("7", "")),
			"8": (self.onKey8, digitHelp.get("8", "")),
			"9": (self.onKey9, digitHelp.get("9", "")),
			"0": (self.onKey0, digitHelp.get("0", "")),
			}, -2)

		# for number key input
		self.setUseableChars(u' 1234567890abcdefghijklmnopqrstuvwxyz')

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey1(self):
		printl("", self, "S")

		self.onNumberKey(1)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey2(self):
		printl("", self, "S")

		self.onNumberKey(2)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey3(self):
		printl("", self, "S")

		self.onNumberKey(3)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey4(self):
		printl("", self, "S")

		self.onNumberKey(4)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey5(self):
		printl("", self, "S")

		self.onNumberKey(5)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey6(self):
		printl("", self, "S")

		self.onNumberKey(6)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey7(self):
		printl("", self, "S")

		self.onNumberKey(7)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey8(self):
		printl("", self, "S")

		self.onNumberKey(8)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey9(self):
		printl("", self, "S")

		self.onNumberKey(9)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onKey0(self):
		printl("", self, "S")

		self.onNumberKey(0)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onNumberKey(self, number):
		printl("", self, "S")

		printl(str(number), self, "I")

		key = self.getKey(number)
		if key is not None:
			keyvalue = key.encode("utf-8") if PY2 else key
			if len(keyvalue) == 1:
				self.onNumberKeyLastChar = keyvalue[0].upper()
				self.onNumberKeyPopup(self.onNumberKeyLastChar, True)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onNumberKeyPopup(self, value, visible):
		printl("", self, "S")

		if visible:
			self["number_key_popup"].setText(value)
			self["number_key_popup"].show()
		else:
			self["number_key_popup"].hide()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def timeout(self):
		"""
		onNumberKeyTimeout
		"""
		printl("", self, "S")

		printl(self.onNumberKeyLastChar, self, "I")
#		if self.onNumberKeyLastChar != ' ':
#			pass
			# filter
#		else:
#			pass
			# reset filter

		self.filter()

		self.onNumberKeyPopup(self.onNumberKeyLastChar, False)
		NumericalTextInput.timeout(self)

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def filter(self):
		printl("", self, "S")

		if self.onNumberKeyLastChar == " ":
			self["menu"].setList(self.beforeFilterListViewList)

			# we also have to reset the variable because this one is passed to player
			self.listViewList = self.beforeFilterListViewList
		else:
			self.listViewList = [x for x in self.beforeFilterListViewList if x[0][0] == self.onNumberKeyLastChar]
			self["menu"].setList(self.listViewList)

		self.refreshMenu()

		printl("", self, "C")
