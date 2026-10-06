# -*- coding: utf-8 -*-
"""PlaybackClock: the position estimate for transcoded HLS.

Measured on the box: during HLS playback getPlayPosition() answers
(-1, garbage) on every tick, so the plugin has to keep the time itself
or the server can never be told where playback is.
"""

import unittest

try:
	from tests import helpers
except ImportError:  # direct invocation from the tests directory
	import helpers

helpers.setup_environment()

from src.__common__ import PlaybackClock


class FakeTime(object):
	def __init__(self, start=1000.0):
		self.now = start

	def __call__(self):
		return self.now

	def sleep(self, seconds):
		self.now += seconds


class TestPlaybackClock(unittest.TestCase):
	def setUp(self):
		self.time = FakeTime()
		self.clock = PlaybackClock(timeSource=self.time)

	def test_counts_seconds_while_running(self):
		self.clock.start(0)
		self.time.sleep(12)

		self.assertEqual(self.clock.tell(), 12)

	def test_starts_from_the_given_position(self):
		self.clock.start(487)  # a resume point
		self.time.sleep(5)

		self.assertEqual(self.clock.tell(), 492)

	def test_pause_freezes_and_resume_continues(self):
		self.clock.start(0)
		self.time.sleep(10)
		self.clock.pause()
		self.time.sleep(60)  # a whole minute paused

		self.assertEqual(self.clock.tell(), 10)

		self.clock.resume()
		self.time.sleep(5)
		self.assertEqual(self.clock.tell(), 15)

	def test_sync_adopts_the_decoder_position(self):
		# plain files have a valid decoder position: it wins over the estimate
		self.clock.start(0)
		self.time.sleep(30)
		self.clock.syncTo(25)
		self.time.sleep(5)

		self.assertEqual(self.clock.tell(), 30)

	def test_sync_while_paused_stays_paused(self):
		self.clock.start(0)
		self.clock.pause()
		self.clock.syncTo(100)
		self.time.sleep(50)

		self.assertEqual(self.clock.tell(), 100)

	def test_relative_jump_moves_the_estimate(self):
		self.clock.start(60)
		self.clock.add(30)  # skip forward

		self.assertEqual(self.clock.tell(), 90)

		self.clock.add(-120)  # skip back past the start
		self.assertEqual(self.clock.tell(), 0)  # clamped, never negative

	def test_double_pause_and_double_resume_are_harmless(self):
		self.clock.start(0)
		self.time.sleep(10)
		self.clock.pause()
		self.clock.pause()
		self.clock.resume()
		self.time.sleep(3)
		self.clock.resume()
		self.time.sleep(2)

		self.assertEqual(self.clock.tell(), 15)


if __name__ == "__main__":
	unittest.main()
