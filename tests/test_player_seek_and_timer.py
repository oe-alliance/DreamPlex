# -*- coding: utf-8 -*-
"""Two things that silently did nothing during transcoded playback.

Both were found in DreamFin (the sibling fork) and were identical here.
Checked on the source: DP_Player pulls in half of enigma2, so it cannot be
imported offline - but these are structural properties, so the AST answers
them.

1. The report timer was created but never started. The four `.start()`
   calls lived elsewhere and none of them won for streamed/transcoded
   playback, so updateTimeline() ran zero times for a whole playback.
2. seekToMinute() delegated to seekToStartPos(), which refuses to seek
   until the decoder reports a position - which on transcoded HLS it never
   does, so the jump was dropped without a word.
"""

import ast
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
PLAYER = os.path.join(SRC, "DP_Player.py")


def parseTree():
	# bytes, so a py2 parser does not trip over the encoding declaration
	handle = io.open(PLAYER, "rb")
	try:
		return ast.parse(handle.read(), filename=PLAYER)
	finally:
		handle.close()


def findFunction(name):
	for node in ast.walk(parseTree()):
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return node

	raise AssertionError("%s() not found in DP_Player.py" % name)


def calledNames(node):
	"""Every attribute call inside a function, as plain names."""
	names = set()
	for child in ast.walk(node):
		if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
			names.add(child.func.attr)

	return names


def callsMethodOn(node, receiver, method):
	"""True when the function calls self.<receiver>.<method>(...).

	Matching the bare method name is not enough here: startTimelineWatcher()
	also calls .start() on the PlaybackClock, which would make a check for
	"start" pass while the timer stays stopped.
	"""
	for child in ast.walk(node):
		if not isinstance(child, ast.Call):
			continue

		func = child.func
		if not isinstance(func, ast.Attribute) or func.attr != method:
			continue

		inner = func.value
		if isinstance(inner, ast.Attribute) and inner.attr == receiver:
			return True

	return False


class TestTimelineWatcherStarts(unittest.TestCase):
	"""The timer has to be started where it is created."""

	def test_watcher_is_started_where_it_is_created(self):
		watcher = findFunction("startTimelineWatcher")

		self.assertTrue(callsMethodOn(watcher, "timelineWatcher", "start"),
				"startTimelineWatcher() creates the eTimer but never starts it, "
				"so nothing reports progress on streamed/transcoded playback")

	def test_watcher_is_created_and_wired_before_starting(self):
		# guards against 'fixing' it by starting a timer that does not exist
		watcher = findFunction("startTimelineWatcher")
		calls = calledNames(watcher)

		self.assertIn("append", calls, "the updateTimeline callback must stay wired")
		self.assertIn("updateTimeline", calls, "report at once, do not wait an interval")

	def test_interval_is_not_repeated_as_a_literal(self):
		# it used to be written out in four places that could disagree
		handle = io.open(PLAYER, "rb")
		try:
			source = handle.read().decode("utf-8")
		finally:
			handle.close()

		self.assertIn("TIMELINE_INTERVAL_MS", source)
		self.assertNotIn("timelineWatcher.start(5000", source,
				"use the module constant instead of repeating the interval")


class TestSeekToMinute(unittest.TestCase):
	"""Manual seek must not depend on a decoder position that never comes."""

	def test_seeks_directly_and_not_through_seekToStartPos(self):
		seekToMinute = findFunction("seekToMinute")
		calls = calledNames(seekToMinute)

		self.assertIn("doSeek", calls,
				"seekToMinute() must jump itself")
		self.assertNotIn("seekToStartPos", calls,
				"seekToStartPos() drops the jump when the decoder has no "
				"position, which on transcoded HLS is always")

	def test_clamps_to_the_end_of_the_media(self):
		seekToMinute = findFunction("seekToMinute")

		self.assertIn("getMediaDuration", calledNames(seekToMinute),
				"a minute past the end has to be clamped")

	def test_survives_a_cancelled_dialog(self):
		# MinuteInput answers None when the user cancels
		seekToMinute = findFunction("seekToMinute")
		source = ast.dump(seekToMinute)

		self.assertIn("None", source,
				"seekToMinute() must tolerate minutes=None")

	def test_seekToStartPos_keeps_its_retry_logic(self):
		# it is still the right thing when resuming AT START of playback
		startPos = findFunction("seekToStartPos")
		calls = calledNames(startPos)

		self.assertIn("getPlayPosition", calls)
		self.assertIn("doSeek", calls)


class TestSeekWatcherDoesNotBlockTheMainLoop(unittest.TestCase):
	"""The resume watcher runs on the enigma2 main loop, not on a thread.

	Despite being called `seekwatcherThread` it is an eTimer, so its callback
	runs on the main loop. It used to hold a `while` loop with a sleep(1) in
	it, which froze the GUI for the whole resume - dropped key presses - and
	never ended at all when the decoder had no position to report.
	"""

	def test_no_sleep_on_the_main_loop(self):
		watcher = findFunction("seekWatcher")

		self.assertNotIn("sleep", calledNames(watcher),
				"seekWatcher() runs on the main loop: a sleep() here freezes "
				"the whole GUI")

	def test_no_loop_waiting_for_the_resume(self):
		watcher = findFunction("seekWatcher")

		loops = [n for n in ast.walk(watcher) if isinstance(n, (ast.While, ast.For))]
		self.assertEqual(loops, [],
				"the eTimer already repeats; looping here blocks the main loop "
				"until the resume completes, or forever if it never does")

	def test_it_still_attempts_the_seek(self):
		watcher = findFunction("seekWatcher")

		self.assertIn("seekToStartPos", calledNames(watcher))

	def test_the_watcher_timer_is_never_replaced_while_alive(self):
		"""evUpdatedInfo fires repeatedly; building a new eTimer each time
		drops the last reference to one whose callback may be on the stack."""
		# the method is name-mangled: _DP_Player__evUpdatedInfo
		updated = None
		for node in ast.walk(parseTree()):
			if isinstance(node, ast.FunctionDef) and node.name.endswith("__evUpdatedInfo"):
				updated = node
				break

		self.assertIsNotNone(updated, "__evUpdatedInfo() not found")

		# The eTimer() call must sit behind a guard on the watcher ITSELF.
		# Checking merely for "None" in the condition is not enough: the
		# outer `if ... resumeStamp is not None ...` would match and the
		# test would pass against the unguarded code.
		guarded = False
		for node in ast.walk(updated):
			if not isinstance(node, ast.If):
				continue

			condition = ast.dump(node.test)
			if "seekwatcherThread" not in condition or "None" not in condition:
				continue

			if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
					and c.func.id == "eTimer" for c in ast.walk(node)):
				guarded = True

		self.assertTrue(guarded,
				"__evUpdatedInfo() must only build the watcher when there is "
				"none yet, never replace a live one")

	def test_the_timer_is_stopped_when_leaving_the_player(self):
		leave = findFunction("leavePlayerConfirmed")

		self.assertTrue(callsMethodOn(leave, "seekwatcherThread", "stop"),
				"nothing else stops the resume watcher, so it would keep "
				"firing after the player is gone")


class TestResumeSurvivesAFailingGetLength(unittest.TestCase):
	"""A failing getLength() must not take the resume down with it.

	`length` was only assigned inside `if not r[0]:` but read further down in
	a log line, so when getLength() failed that read raised NameError, the
	function's own `except` swallowed it, and the resume was silently lost.
	Reported by the DreamFin fork, which carries the same code.
	"""

	def test_length_is_initialised_before_getLength(self):
		startPos = findFunction("seekToStartPos")

		assigned = []
		for node in ast.walk(startPos):
			if isinstance(node, ast.Assign):
				for target in node.targets:
					if isinstance(target, ast.Name):
						assigned.append(target.id)

		self.assertGreaterEqual(assigned.count("length"), 2,
				"length must have a default before the conditional assignment, "
				"otherwise a failing getLength() raises NameError and the "
				"resume is lost")

	def test_log_line_does_not_print_the_time_function(self):
		handle = io.open(PLAYER, "rb")
		try:
			source = handle.read().decode("utf-8")
		finally:
			handle.close()

		# `time` is the imported function: this logged "<built-in function time>"
		self.assertNotIn('"seeking to " + str(time)', source)


if __name__ == "__main__":
	unittest.main()
