# -*- coding: utf-8 -*-
"""Stub of enigma2's Components.SystemInfo."""

_ITEMS = {
	"displaybrand": "TestBrand",
	"model": "testbox",
	"architecture": "mips32el",
	"oe": "OpenATV-test",
}


class _BoxInfo(object):
	def getItem(self, key, default=None):
		return _ITEMS.get(key, default)


BoxInfo = _BoxInfo()
