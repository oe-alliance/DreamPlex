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
from Components.config import config
from . import Singleton

from .DP_View import DP_View

from .__common__ import printl2 as printl, encodeThat
from . import _  # _ is translation

#===============================================================================
#
#===============================================================================


def getViewClass():
	printl("", __name__, "S")

	printl("", __name__, "C")
	return DPS_ViewShows

#===============================================================================
#
#===============================================================================


class DPS_ViewShows(DP_View):

	parentSeasonId = None
	grandparentTitle = None

	#===========================================================================
	#
	#===========================================================================
	def __init__(self, viewClass, libraryName, loadLibraryFnc, viewParams):
		printl("", self, "S")

		DP_View.__init__(self, viewClass, libraryName, loadLibraryFnc, viewParams)

		self.setTitle(_("Shows"))

		self.playTheme = Singleton().getSettingsInstance().playTheme.getValue()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _refresh(self):
		printl("", self, "S")
		# we have to reset it here
		self.themeMusicIsRunning = False

		# for all view steps
		self["title"].setText(encodeThat(self.details.get("title", " ")))
		self["tag"].setText(encodeThat(self.details.get("tagline", " ")))
		self["shortDescription"].setText(encodeThat(self.details.get("summary", " ")))

		self.setDuration()
		self.setMediaFunctions()

		if self.details["currentViewMode"] == "ShowShows":
			printl("is ShowShows", self, "D")
			#self.setTitle(str(self.mediaContainer.get("title2", " ")))
			self["leafCount"].setText(self.details.get("leafCount", " "))
			self["viewedLeafCount"].setText(self.details.get("viewedLeafCount", " "))
			self["unviewedLeafCount"].setText(str(int(self.details.get("leafCount", " ")) - int(self.details.get("viewedLeafCount", " "))))
			self["childCount"].setText(str(self.details.get("childCount", " ")))
			self["studio"].setText(encodeThat(self.details.get("studio", " ")))
			self["genre"].setText(self.details.get("genre", " "))
			self["year"].setText(str(self.details.get("year", " - ")))

			self.parentSeasonId = self.details["ratingKey"]

			self.bname = self.details["ratingKey"]
			self.pname = self.details["ratingKey"]

			self.changeBackdrop = True
			self.changePoster = True
			self.resetPoster = True
			self.resetBackdrop = True

			# if we are a show an if playtheme is enabled we start playback here
			if self.playTheme and "theme" in self.details:
				self.startThemePlayback()

			if self.tagType != self.lastTagType:
				self.hideMediaFunctions()

			self.handlePopularityPixmaps()
			self.handleRatedPixmaps()

			# we use this for filtermode at startup
			self.filterableContent = True

		elif self.details["currentViewMode"] == "ShowSeasons":
			printl("is ShowSeasons", self, "D")
			printl("self.mediaContainer: " + str(self.mediaContainer), self, "D")

			if self.mediaContainer["title2"] == self.details["title"]:
				self.grandparentTitle = str(self.mediaContainer.get("title1", " "))
			else:
				self.grandparentTitle = str(self.mediaContainer.get("title2", " "))

			self["grandparentTitle"].setText(self.grandparentTitle)

			self["leafCount"].setText(self.details.get("leafCount", " "))
			self["viewedLeafCount"].setText(self.details.get("viewedLeafCount", " "))
			self["unviewedLeafCount"].setText(str(int(self.details.get("leafCount", " ")) - int(self.details.get("viewedLeafCount", " "))))
			self["childCount"].setText(str(self.details.get("childCount", " ")))

			self.parentSeasonNr = self.details["ratingKey"]
			# self.parentSeasonId is only ever set a few lines up, in the
			# "ShowShows" branch (the show's own list row) - normally
			# already run by the time a season list renders, since you
			# always pass through it first. Landing straight on a show's
			# seasons (DP_ServerMenu's hero "Open series" - see
			# _playHeroItem()) skips that step entirely, leaving it at its
			# class default (None) and crashing the str concatenation a few
			# lines down in getPictureInformationToLoad() - falls back to
			# this season's own ratingKey instead, same idea (a stable per-
			# item cache key), not the crash.
			self.bname = self.parentSeasonId if self.parentSeasonId is not None else self.details["ratingKey"]
			self.pname = self.details["ratingKey"]

			self.changeBackdrop = True
			self.changePoster = True
			self.resetPoster = False
			self.resetBackdrop = False

			if self.tagType != self.lastTagType:
				self.hideMediaFunctions()

			# we use this for filtermode at startup
			self.filterableContent = False

		elif self.details["currentViewMode"] == "ShowEpisodes" or self.details["currentViewMode"] == "ShowEpisodesDirect":
			printl("is ShowEpisodes", self, "D")
			self["tag"].setText(str(self.mediaContainer.get("title2", " ")))
			self["writer"].setText(encodeThat(self.details.get("writer", " ")))

			if self.details["currentViewMode"] == "ShowEpisodesDirect":
				self["tag"].setText("Season: " + encodeThat(self.details.get("parentIndex", " ")))
				self["title"].setText(str(self.details.get("grandparentTitle", " ")))
			else:
				if self.grandparentTitle is not None:
					self["grandparentTitle"].setText(self.grandparentTitle)
					#self.setTitle(self.grandparentTitle)

			# technical details
			self.mediaDataArr = self.details["mediaDataArr"][0]
			self.parts = self.mediaDataArr["Parts"][0]

			self["videoCodec"].setText(self.mediaDataArr.get("videoCodec", " - "))
			self["bitrate"].setText(self.mediaDataArr.get("bitrate", " - "))
			self["videoFrameRate"].setText(self.mediaDataArr.get("videoFrameRate", " - "))
			self["audioChannels"].setText(self.mediaDataArr.get("audioChannels", " - "))
			self["aspectRatio"].setText(self.mediaDataArr.get("aspectRatio", " - "))
			self["videoResolution"].setText(self.mediaDataArr.get("videoResolution", " - "))
			self["audioCodec"].setText(self.mediaDataArr.get("audioCodec", " - "))
			self["file"].setText(encodeThat(self.parts.get("file", " - ")))

			self.bname = self.details["ratingKey"]
			if self.details["currentViewMode"] == "ShowEpisodesDirect":
				self.pname = self.details["grandparentRatingKey"]
			else:
				self.pname = self.details["parentRatingKey"]

			if self.currentViewType == "Backdrop":
				#we change this because the backdrops of episodes are low quality and will be very pixi
				self.changeBackdrop = False
			else:
				self.changeBackdrop = True

			self.changePoster = True
			self.resetPoster = False
			self.resetBackdrop = False

			if self.fastScroll == False or self.showMedia == True:
				# handle all pixmaps
				self.handlePopularityPixmaps()
				self.handleCodecPixmaps()
				self.handleAspectPixmaps()
				self.handleResolutionPixmaps()
				self.handleSoundPixmaps()
				self.handleSoundChannelsPixmaps()

			if self.tagType != self.lastTagType:
				self.showMediaFunctions()

			# we use this for filtermode at startup
			self.filterableContent = True

		else:
			raise Exception

		# now gather information for pictures
		self.getPictureInformationToLoad()

		# reset leaving here for next run
		self.leaving = False

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def onLeave(self):
		printl("", self, "S")

		# first we call the the rest of the onEnter from super
		super(DPS_ViewShows, self).onLeave()

		# first restore Elements
		self.restoreElementsInViewStep()

		# the lastTagType will be reset every time we switch to another view step
		self.lastTagType = None

		# we do the refresh here to be able to handle directory content
		self.refresh()

		printl("", self, "C")
