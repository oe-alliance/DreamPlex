# -*- coding: utf-8 -*-
"""Functional stub of enigma2's Components.config.

Only implements the tiny surface DreamPlex uses: config elements carry a
mutable ``value`` plus no-op ``save``/``load``, subsections accept free
attribute assignment, and ``ConfigSubList`` behaves like a list.
"""


class ConfigElement(object):
	def __init__(self, default=None, **kwargs):
		self.value = default
		self.default = default

	def save(self):
		pass

	def load(self):
		pass

	def cancel(self):
		pass

	def setValue(self, value):
		self.value = value

	def getValue(self):
		return self.value


class ConfigYesNo(ConfigElement):
	def __init__(self, default=False, **kwargs):
		ConfigElement.__init__(self, default=default, **kwargs)


class ConfigText(ConfigElement):
	def __init__(self, default="", **kwargs):
		ConfigElement.__init__(self, default=default, **kwargs)


class ConfigDirectory(ConfigText):
	pass


class ConfigPassword(ConfigText):
	pass


class ConfigSelection(ConfigElement):
	def __init__(self, default=None, choices=None, **kwargs):
		ConfigElement.__init__(self, default=default, **kwargs)
		self.choices = choices or []


class ConfigInteger(ConfigElement):
	def __init__(self, default=0, limits=None, **kwargs):
		ConfigElement.__init__(self, default=default, **kwargs)
		self.limits = limits


class ConfigPIN(ConfigInteger):
	pass


class ConfigNumber(ConfigInteger):
	pass


class ConfigIP(ConfigElement):
	def __init__(self, default=None, **kwargs):
		if default is None:
			default = [0, 0, 0, 0]
		ConfigElement.__init__(self, default=default, **kwargs)


class ConfigSubsection(object):
	def save(self):
		pass

	def load(self):
		pass


class ConfigSubList(list):
	def save(self):
		pass


class _ConfigRoot(ConfigSubsection):
	pass


config = _ConfigRoot()
config.plugins = ConfigSubsection()


class _ConfigFile(object):
	def save(self):
		pass

	def load(self):
		pass


configfile = _ConfigFile()


def getConfigListEntry(*args):
	return tuple(args)


class NumericalTextInput(object):
	def __init__(self, *args, **kwargs):
		pass
