# -*- coding: utf-8 -*-
"""Minimal stub of the enigma2 C module so DreamPlex modules can be
imported in a plain CPython interpreter (offline test harness)."""


class _Size(object):
	def width(self):
		return 1280

	def height(self):
		return 720


class _Desktop(object):
	def size(self):
		return _Size()


def getDesktop(which=0):
	return _Desktop()


def addFont(*args, **kwargs):
	pass


def loadPNG(*args, **kwargs):
	return None


def loadJPG(*args, **kwargs):
	return None


class eTimer(object):
	def __init__(self, *args, **kwargs):
		self.callback = []

	def start(self, *args, **kwargs):
		pass

	def stop(self):
		pass


class eSize(object):
	def __init__(self, w=0, h=0):
		self._w = w
		self._h = h


class eServiceReference(object):
	def __init__(self, *args, **kwargs):
		pass


class ePicLoad(object):
	def __init__(self, *args, **kwargs):
		pass


class ePythonMessagePump(object):
	def __init__(self, *args, **kwargs):
		self.recv_msg = _Signal()

	def send(self, *args):
		pass


class _Signal(object):
	def get(self):
		return []


class eWidget(object):
	def __init__(self, *args, **kwargs):
		pass


class eListboxPythonMultiContent(object):
	def __init__(self, *args, **kwargs):
		pass


class eLabel(object):
	def __init__(self, *args, **kwargs):
		pass


class gFont(object):
	def __init__(self, *args, **kwargs):
		pass


class eConsoleAppContainer(object):
	def __init__(self, *args, **kwargs):
		pass


class iPlayableService(object):
	evStart = 1
	evEOF = 2
	evUpdatedInfo = 3


class eServiceCenter(object):
	@staticmethod
	def getInstance():
		return None


class iServiceInformation(object):
	sTitle = 1


class eDVBVolumecontrol(object):
	@staticmethod
	def getInstance():
		return None


RT_HALIGN_LEFT = 0
RT_HALIGN_RIGHT = 1
RT_HALIGN_CENTER = 2
RT_VALIGN_CENTER = 4
