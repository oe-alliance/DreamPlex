# -*- coding: utf-8 -*-
"""Stub of twisted.web.client."""


class _Deferred(object):
	def addCallback(self, *a, **k):
		return self

	def addErrback(self, *a, **k):
		return self


def downloadPage(*a, **k):
	return _Deferred()
