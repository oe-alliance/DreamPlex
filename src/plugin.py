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
from __future__ import annotations
from typing import TYPE_CHECKING

from Plugins.Plugin import PluginDescriptor
from Screens.Standby import inStandby
from . import Singleton, SettingsStorage
from .DPH_RemoteListener import HttpDaemon

try:
	from Components.Network import iNetworkInfo
except Exception:
	from Components.Network import iNetwork

from .DP_Player import DP_Player
from enigma import eTimer

from . import prepareEnvironment, startEnvironment, initSettingsStorage, _ # _ is translation
from .__common__ import getUUID, saveLiveTv, getLiveTv, getBoxResolution, getVersion

# StartEnigma is enigma2's own startup script, run as __main__ at boot - it is
# never left behind in sys.modules under the name "StartEnigma", and its
# module body unconditionally calls e2reactor.install(). A plain
# "from StartEnigma import Session" here therefore re-imports and re-executes
# that whole script, hitting the already-installed reactor and crashing with
# ReactorAlreadyInstalledError, which enigma2's plugin loader reports as
# "Extensions/DreamPlex (reactor already installed)". Session is only used
# below as a type annotation, so it is deferred to TYPE_CHECKING instead.
if TYPE_CHECKING:
	from StartEnigma import Session

#===============================================================================
# GLOBALS
#===============================================================================


class GlobalVars:
	def __init__(self):
		self.lastKey: int | None = None
		self.global_session: Session | None = None
		self.HttpDaemonThread: HttpDaemon | None = None
		self.HttpDaemonStarted: bool = False
		self.notifyWatcher: eTimer = None


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

	settings: SettingsStorage = Singleton().getSettingsInstance()

	if reason == 0:
		prepareEnvironment()
		getUUID()

	else:
		settings.writeToFile()

		if settings.remoteAgent.getValue() and globalvars.HttpDaemonStarted:
			globalvars.HttpDaemonThread.stopRemoteDaemon()

#===========================================================================
#
#===========================================================================


def startRemoteDaemon():
	from .DPH_RemoteListener import HttpDaemon

	globalvars.HttpDaemonThread = HttpDaemon()

	globalvars.HttpDaemonThread.PlayerDataPump.recv_msg.get().append(gotThreadMsg)

	globalvars.HttpDaemonThread.prepareDaemon() # we just prepare. we are starting only on networkStart with HttpDaemonThread.setSession
	globalvars.HttpDaemonStarted = globalvars.HttpDaemonThread.getDaemonState()[1]

	if globalvars.HttpDaemonStarted:
		globalvars.HttpDaemonThread.setSession(globalvars.global_session)

#===========================================================================
#
#===========================================================================


def getHttpDaemonInformation():
	return globalvars.HttpDaemonThread.getDaemonState()


#===========================================================================
# msg as second params is needed -. do not remove even if it is not used
# form outside!!!!
#===========================================================================
# noinspection PyUnusedLocal


def gotThreadMsg(msg):
	_msg = globalvars.HttpDaemonThread.PlayerData.pop()

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

			globalvars.HttpDaemonThread.addSubscriber(protocol, host, port, uuid, commandID)
			startNotifier()

		elif command == "removeSubscriber":
			print("remove subscriber")
			uuid = data["uuid"]

			globalvars.HttpDaemonThread.removeSubscriber(uuid)
			updateNotifier()

		elif command == "updateCommandId":
			uuid = data["uuid"]
			commandID = data["commandID"]
			globalvars.HttpDaemonThread.updateCommandID(uuid, commandID)

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
	print("subscribers: " + str(globalvars.HttpDaemonThread.getSubscribersList()))

	if players:
		globalvars.HttpDaemonThread.notifySubscribers(players)

#===========================================================================
#
#===========================================================================


def getPlayer():
	ret = None

	try:
		ret = {}
		ret = globalvars.global_session.current_dialog.getPlayer()
	except Exception:
		pass

	return ret

#===========================================================================
#
#===========================================================================


def sessionStart(reason, **kwargs):

	if "session" in kwargs:
		globalvars.global_session = kwargs["session"]

		if Singleton().getSettingsInstance().remoteAgent.getValue():
			startRemoteDaemon()

		# load skin data here as well
		startEnvironment()

		_offerRestartAfterUpdate(kwargs["session"])

#===========================================================================
# An installed/updated .ipk only replaces the files on disk - Python keeps
# running the already-imported (old) modules until enigma2's GUI process
# itself restarts, so a plugin update has no visible effect until the user
# thinks to do that manually. Detect the version bump here (once per GUI
# session, since sessionStart only fires once) and offer to do it for them.
#===========================================================================


def _offerRestartAfterUpdate(session):
	settings: SettingsStorage = Singleton().getSettingsInstance()
	currentVersion = getVersion()
	lastSeenVersion = settings.lastSeenVersion.getValue()

	settings.lastSeenVersion.setValue(currentVersion)
	settings.writeToFile()

	# Empty lastSeenVersion means a fresh install, not an update - nothing to
	# restart into, so nothing to ask about.
	if lastSeenVersion and lastSeenVersion != currentVersion:
		from Screens.MessageBox import MessageBox

		session.openWithCallback(_onRestartAnswer, MessageBox,
			_("DreamPlex was updated to version %s.\nRestart the GUI now to apply it?") % currentVersion,
			MessageBox.TYPE_YESNO, timeout=20, default=True)

#===========================================================================
#
#===========================================================================


def _onRestartAnswer(confirmed):
	if confirmed and globalvars.global_session is not None:
		from Screens.Standby import TryQuitMainloop

		globalvars.global_session.open(TryQuitMainloop, 3)

#===============================================================================
# plugins
# Actions to take place in Plugins
#===============================================================================
#noinspection PyUnusedLocal


def Plugins(**kwargs):
	myList = []
	boxResolution = getBoxResolution()

	# enigma2 calls Plugins() to build the menu/descriptor list before it ever
	# runs the WHERE_AUTOSTART descriptor below, so Autostart()'s
	# prepareEnvironment() (which creates the settings singleton) has not run
	# yet. showInMainMenu below needs a live settings instance, so create one
	# here if it doesn't exist; Autostart() will still (re)run
	# prepareEnvironment() normally once enigma2 actually starts up.
	if Singleton().getSettingsInstance() is None:
		initSettingsStorage()

	if boxResolution == "FHD":
		myList.append(PluginDescriptor(name="DreamPlex", description="plex client for enigma2", where=[PluginDescriptor.WHERE_PLUGINMENU], icon="pluginLogoHD.png", fnc=main))
	else:
		myList.append(PluginDescriptor(name="DreamPlex", description="plex client for enigma2", where=[PluginDescriptor.WHERE_PLUGINMENU], icon="pluginLogo.png", fnc=main))
	myList.append(PluginDescriptor(where=PluginDescriptor.WHERE_AUTOSTART, fnc=Autostart))
	myList.append(PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionStart))

	if Singleton().getSettingsInstance().showInMainMenu.getValue():
		myList.append(PluginDescriptor(name="DreamPlex", description=_("plex client for enigma2"), where=[PluginDescriptor.WHERE_MENU], fnc=menu_dreamplex))

	return myList
