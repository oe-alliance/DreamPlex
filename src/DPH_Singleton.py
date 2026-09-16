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
from __future__ import annotations

from typing import TYPE_CHECKING

# Imported for the annotations only. Doing it at runtime would create a cycle
# (__init__ -> DPH_Singleton -> DP_SettingsStorage -> __init__), which is why
# these names used to be pulled in through a "DreamPlex.src" package that does
# not exist once the plugin is installed. With the annotations lazy, no import
# is needed at run time at all.
if TYPE_CHECKING:
	from .DP_MediaLibrary import DP_MediaLibrary
	from .DP_SettingsStorage import SettingsStorage


#===============================================================================
# IMPORT
#===============================================================================
#from Plugins.Extensions.DreamPlex.__common__ import printl2 as printl

#===============================================================================
#
#===============================================================================


class Singleton(object):
	"""
	singlton config object
	"""
	__we_are_one: dict = {}
	__mediaLibraryInstance: DP_MediaLibrary = None
	__logFileInstance = ""
	__skinParamsInstance = ""
	__settingsInstance: SettingsStorage = None

	def __init__(self):
		#implement the borg patter (we are one)
		self.__dict__ = self.__we_are_one

	def getMediaLibrary(self, value: DP_MediaLibrary = None) -> DP_MediaLibrary:
		"""with value you can set the singleton content"""
		if value:
			self.__mediaLibraryInstance = value
		else:
			pass

		return self.__mediaLibraryInstance

	def getLogFileInstance(self, value=None):
		"""with value you can set the singleton content"""
		if value:
			#printl("generating Logfile instance ...", self, "D")
			self.__logFileInstance = value
		else:
			#printl("reusing Logfile instance ...", self, "D")
			pass

		return self.__logFileInstance

	def getSkinParamsInstance(self, value=None):
		"""with value you can set the singleton content"""
		if value:
			#printl("generating skinParam instance ...", self, "D")
			self.__skinParamsInstance = value
		else:
			#printl("reusing skinParam instance ...", self, "D")
			pass

		return self.__skinParamsInstance

	def getSettingsInstance(self, value:SettingsStorage=None) -> SettingsStorage:
		if value:
			self.__settingsInstance = value
		else:
			pass

		return self.__settingsInstance
