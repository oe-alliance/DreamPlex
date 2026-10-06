# -*- coding: utf-8 -*-
"""Stub of enigma2's Screens.Screen."""


class Screen(object):
	def __init__(self, session=None, *args, **kwargs):
		self.session = session
		self.onLayoutFinish = []
		self.onFirstExecBegin = []
		self.onClose = []

	def close(self, *args):
		pass

	def setTitle(self, title):
		pass
