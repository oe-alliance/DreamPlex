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
from Plugins.Plugin import PluginDescriptor
from Screens.Standby import inStandby

try:
	from Components.Network import iNetworkInfo
except:
	from Components.Network import iNetwork

from Components.config import config, configfile

from .DP_Player import DP_Player
from enigma import eTimer

from .__init__ import prepareEnvironment, startEnvironment, _ # _ is translation
from .__common__ import getUUID, saveLiveTv, getLiveTv, getBoxResolution

#===============================================================================
# GLOBALS
#===============================================================================


class GlobalVars:
	def __init__(self):
		self.lastKey = None
		self.global_session = None
		self.HttpDeamonThread = None
		self.HttpDeamonThreadConn = None
		self.HttpDeamonStarted = False
		self.notifyWatcher = None
		self.notifyWatcherConn = None


globalvars = GlobalVars()

#===============================================================================
# main
# Actions to take place when starting the plugin over extensions
#===============================================================================
#noinspection PyUnusedLocal


def main(session, **kwargs):
	session.open(DPS_MainMenu)

#===========================================================================
#
#===========================================================================


def DPS_MainMenu(*args, **kwargs):
	from . import DP_MainMenu

 	# this loads the skin
	startEnvironment()

	return DP_MainMenu.DPS_MainMenu(*args, **kwargs)

#===========================================================================
#
#===========================================================================
#noinspection PyUnusedLocal


def menu_dreamplex(menuid, **kwargs):
	if menuid == "mainmenu":
		return [(_("DreamPlex"), main, "dreamplex", 47)]
	return []

#===========================================================================
#
#===========================================================================
#noinspection PyUnusedLocal


def Autostart(reason, session=None, **kwargs):

	if reason == 0:
		# This runs while enigma2 reads the plugin list at boot, so anything
		# raising here takes the whole GUI down with it and leaves the box
		# unusable (that is exactly what a stdlib symbol removed in a newer
		# Python once did). A broken plugin must disable itself, not the
		# receiver - so swallow it and report it loudly instead.
		try:
			prepareEnvironment()
			getUUID()
		except Exception as e:
			print("[DreamPlex] autostart failed, plugin disabled for this boot: %s" % str(e))
			import traceback
			traceback.print_exc()

	else:
		config.plugins.dreamplex.entriescount.save()
		config.plugins.dreamplex.Entries.save()
		config.plugins.dreamplex.save()
		configfile.save()

		if config.plugins.dreamplex.remoteAgent.value and globalvars.HttpDeamonStarted:
			globalvars.HttpDeamonThread.stopRemoteDeamon()

#===========================================================================
#
#===========================================================================


def startRemoteDeamon():
	from .DPH_RemoteListener import HttpDeamon

	globalvars.HttpDeamonThread = HttpDeamon()

	globalvars.HttpDeamonThread.PlayerDataPump.recv_msg.get().append(gotThreadMsg)

	globalvars.HttpDeamonThread.prepareDeamon() # we just prepare. we are starting only on networkStart with HttpDeamonThread.setSession
	globalvars.HttpDeamonStarted = globalvars.HttpDeamonThread.getDeamonState()[1]

	if globalvars.HttpDeamonStarted:
		globalvars.HttpDeamonThread.setSession(globalvars.global_session)

#===========================================================================
#
#===========================================================================


def getHttpDeamonInformation():
	return globalvars.HttpDeamonThread.getDeamonState()


#===========================================================================
# msg as second params is needed -. do not remove even if it is not used
# form outside!!!!
#===========================================================================
# noinspection PyUnusedLocal


def gotThreadMsg(msg):
	_msg = globalvars.HttpDeamonThread.PlayerData.pop()

	data = _msg[0]
	print("data ==>")
	print(str(data))

	# first we check if we are standby and exit this if needed
	if inStandby is not None:
		inStandby.Power()

	if "command" in data:
		command = data["command"]
		if command == "startNotifier":
			startNotifier()

		elif command == "playMedia":
			if data["currentKey"] != globalvars.lastKey:
				startPlayback(data)
			else:
				print("dropping mediaplay command ...")

			globalvars.lastKey = data["currentKey"]

		elif command == "pause":
			if isinstance(globalvars.global_session.current_dialog, DP_Player):
				globalvars.global_session.current_dialog.pauseService()

		elif command == "play":
			if isinstance(globalvars.global_session.current_dialog, DP_Player):
				globalvars.global_session.current_dialog.unPauseService()

		elif command == "skipNext":
			globalvars.global_session.current_dialog.playNextEntry()

		elif command == "skipPrevious":
			globalvars.global_session.current_dialog.playPreviousEntry()

		elif command == "stepForward":
			globalvars.global_session.current_dialog.seekFwd()

		elif command == "stepBack":
			globalvars.global_session.current_dialog.seekBack()

		elif command == "seekTo":
			offset = int(data["offset"]) * 90000
			globalvars.global_session.current_dialog.doSeek(offset)

		elif command == "setVolume":
			if isinstance(globalvars.global_session.current_dialog, DP_Player):
				globalvars.global_session.current_dialog.setVolume(int(data["volume"]))

		elif command == "stop":
			globalvars.lastKey = None
			stopPlayback(restartLiveTv=True)

		elif command == "addSubscriber":
			print("subscriber")
			protocol = data["protocol"]
			host = data["host"]
			port = data["port"]
			uuid = data["uuid"]
			commandID = data["commandID"]

			globalvars.HttpDeamonThread.addSubscriber(protocol, host, port, uuid, commandID)
			startNotifier()

		elif command == "removeSubscriber":
			print("remove subscriber")
			uuid = data["uuid"]

			globalvars.HttpDeamonThread.removeSubscriber(uuid)
			updateNotifier()

		elif command == "updateCommandId":
			uuid = data["uuid"]
			commandID = data["commandID"]
			globalvars.HttpDeamonThread.updateCommandID(uuid, commandID)

		elif command == "idle":
			pass

		else:
			# not handled command
			print(command)
			raise Exception

#===========================================================================
#
#===========================================================================


def startPlayback(data, stopPlaybackFirst=False):
	listViewList = data["listViewList"]
	currentIndex = data["currentIndex"]
	libraryName = data["libraryName"]
	autoPlayMode = data["autoPlayMode"]
	resumeMode = data["resumeMode"]
	playbackMode = data["playbackMode"]
	forceResume = data["forceResume"]
	subtitleData = data["subtitleData"]

	if stopPlaybackFirst:
		stopPlayback()

	# save liveTvData
	saveLiveTv(globalvars.global_session.nav.getCurrentlyPlayingServiceReference())

	if not isinstance(globalvars.global_session.current_dialog, DP_Player):
		# now we start the player
		globalvars.global_session.open(DP_Player, listViewList, currentIndex, libraryName, autoPlayMode, resumeMode, playbackMode, forceResume=forceResume, subtitleData=subtitleData, startedByRemotePlayer=True)

#===========================================================================
#
#===========================================================================


def stopPlayback(restartLiveTv=False):

	if isinstance(globalvars.global_session.current_dialog, DP_Player):
		globalvars.global_session.current_dialog.leavePlayerConfirmed(True)
		globalvars.global_session.current_dialog.close((True,))

	if restartLiveTv:
		restartLiveTvNow()

#===========================================================================
#
#===========================================================================


def restartLiveTvNow():
	globalvars.global_session.nav.playService(getLiveTv())

#===========================================================================
#
#===========================================================================


def startNotifier():

	globalvars.notifyWatcher = eTimer()
	globalvars.notifyWatcher.callback.append(notifySubscribers)
	globalvars.notifyWatcher.start(1000, False)

#===========================================================================
#
#===========================================================================


def updateNotifier():
	if globalvars.notifyWatcher is not None:
		players = getPlayer()
		if not players:
			globalvars.notifyWatcher.stop()

#===========================================================================
#
#===========================================================================


def notifySubscribers():
	players = getPlayer()
	print("subscribers: " + str(globalvars.HttpDeamonThread.getSubscribersList()))

	if players:
		globalvars.HttpDeamonThread.notifySubscribers(players)

#===========================================================================
#
#===========================================================================


def getPlayer():
	ret = None

	try:
		ret = {}
		ret = globalvars.global_session.current_dialog.getPlayer()
	except:
		pass

	return ret

#===========================================================================
#
#===========================================================================


def sessionStart(reason, **kwargs):

	if "session" in kwargs:
		globalvars.global_session = kwargs["session"]

		# same reasoning as in Autostart(): a failure while the GUI session
		# starts must not stop enigma2 from coming up
		try:
			if config.plugins.dreamplex.remoteAgent.value:
				startRemoteDeamon()

			# load skin data here as well
			startEnvironment()
		except Exception as e:
			print("[DreamPlex] session start failed, plugin disabled for this boot: %s" % str(e))
			import traceback
			traceback.print_exc()

#===============================================================================
# plugins
# Actions to take place in Plugins
#===============================================================================
#noinspection PyUnusedLocal


def Plugins(**kwargs):
	myList = []
	boxResolution = getBoxResolution()

	if boxResolution == "FHD":
		myList.append(PluginDescriptor(name="DreamPlex", description=_("plex client for enigma2"), where=[PluginDescriptor.WHERE_PLUGINMENU], icon="pluginLogoHD.png", fnc=main))
	else:
		myList.append(PluginDescriptor(name="DreamPlex", description=_("plex client for enigma2"), where=[PluginDescriptor.WHERE_PLUGINMENU], icon="pluginLogo.png", fnc=main))
	myList.append(PluginDescriptor(where=PluginDescriptor.WHERE_AUTOSTART, fnc=Autostart))
	myList.append(PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionStart))

	if config.plugins.dreamplex.showInMainMenu.value:
		myList.append(PluginDescriptor(name="DreamPlex", description=_("plex client for enigma2"), where=[PluginDescriptor.WHERE_MENU], fnc=menu_dreamplex))

	return myList
