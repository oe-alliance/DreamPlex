# -*- coding: utf-8 -*-
"""The letter filter of the library view, tested on the real methods.

DP_View cannot be imported here - it pulls in the player and, through it,
InfoBarGenerics - so each method is compiled from the source (every
FunctionDef of the class goes through compile/exec with stubs for printl, _,
runInThread and friends) and run on a stand-in for the screen. Only the
periphery the filter does not depend on is stubbed: images, skin levels,
timers. refresh() keeps the one part that matters here - which entry is
selected and the seen/unseen state derived from it.

Every case runs with two models of the listbox. One sends the cursor to the
top on every new list, so nothing can pass by leaning on a cursor that
happened to survive a list swap. The other does what the receiver really
does - on OpenATV 7.0 a new list keeps the cursor's index, cut down to its
length - so nothing can pass by leaning on a reset either. One model alone
hides half: the resetting one hid that filtering again after RED landed on
the last row. The handler of the RED button in filter mode is read from the
setColorFunction(color="red", level="4") call in the source, which keeps
this file valid before and after that button changes target.

What is checked is what the user sees: which icon the whole list paints once
the filter is cleared, which list is on screen after leaving the filter mode,
what the yellow button says.

Found by the DreamFin fork on OpenATV 7.0 and reproduced on the receiver
here: a row marked as seen while a letter filter was active came back with
the old icon once the filter was cleared.
"""

import ast
import io
import os
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

SEEN, UNSEEN, STARTED = "icon:seen", "icon:unseen", "icon:started"

PENDING = []  # callbacks captured by the stand-in runInThread


def _printl(*args, **kwargs):
	pass


def _translate(text):
	return text


def _fireAndForget(*args, **kwargs):
	pass


def _runInThread(work, callback):
	PENDING.append(callback)


class _Plex(object):
	http = "http"

	def getMoviesFromSection(self, url):
		raise AssertionError("the tests answer for the server themselves")


class _Singleton(object):
	def getPlexInstance(self):
		return _Plex()


GLOBALS = {
	"printl": _printl, "_": _translate, "fireAndForget": _fireAndForget,
	"runInThread": _runInThread, "Singleton": _Singleton,
}


def literalOf(node):
	if hasattr(ast, "Constant") and isinstance(node, ast.Constant):
		return node.value
	if hasattr(ast, "Str") and isinstance(node, ast.Str):
		return node.s
	return None


def loadClass(filename, classname):
	"""(class node, {name: function}) compiled from the real source."""
	path = os.path.join(SRC, filename)
	handle = io.open(path, "rb")
	try:
		tree = ast.parse(handle.read(), filename=path)
	finally:
		handle.close()

	found = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == classname]
	assert found, "class %s not found in %s" % (classname, filename)
	cls = found[0]

	methods = {}
	for node in cls.body:
		if not isinstance(node, ast.FunctionDef) or node.name.startswith("__"):
			continue
		node.decorator_list = []
		module = ast.Module(body=[node])
		module.type_ignores = []
		namespace = dict(GLOBALS)
		try:
			exec(compile(module, path, "exec"), namespace)
		except NameError:
			continue  # a default argument needs the real module; not used here
		methods[node.name] = namespace[node.name]

	return cls, methods


VIEW_CLASS, VIEW_METHODS = loadClass("DP_View.py", "DP_View")
FILTER_CLASS, FILTER_METHODS = loadClass("DPH_ScreenHelper.py", "DPH_Filter")


def redHandlerInFilterMode():
	"""Name of the method the RED button calls on level 4 (the filter mode)."""
	for node in ast.walk(VIEW_CLASS):
		if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "setColorFunction"):
			continue
		keywords = dict((k.arg, k.value) for k in node.keywords)
		if literalOf(keywords.get("color")) == "red" and literalOf(keywords.get("level")) == "4":
			return keywords["functionList"].elts[1].attr

	raise AssertionError("no setColorFunction(color='red', level='4') in DP_View.py")


class _Listbox(object):
	"""An enigma2 listbox as far as the view uses it. A new list sends the
	cursor to the top, and getCurrent() hands back the stored row itself."""

	def __init__(self):
		self.list = []
		self.index = 0

	def setList(self, rows):
		self.list = rows
		self.index = 0

	def getCurrent(self):
		if 0 <= self.index < len(self.list):
			return self.list[self.index]
		return None

	def getIndex(self):
		return self.index

	def setIndex(self, index):
		self.index = index


class _ClampingListbox(_Listbox):
	"""The listbox the receiver really has, as seen on OpenATV 7.0: a new
	list keeps the cursor's index, cut down to the length of the new list.
	"""

	def setList(self, rows):
		self.list = rows
		self.index = min(self.index, max(len(rows) - 1, 0))


class _Label(object):
	def __init__(self):
		self.text = ""
		self.visible = True

	def setText(self, text):
		self.text = text

	def getText(self):
		return self.text

	def show(self):
		self.visible = True

	def hide(self):
		self.visible = False


class FakeView(object):
	seenPic, unseenPic, startedPic = SEEN, UNSEEN, STARTED
	seenUrl = unseenUrl = "/:/scrobble"
	keyOneDisabled = False
	filterMode = False
	currentFunctionLevel = "1"
	forceUpdate = False
	selection = None
	seen = False
	onNumberKeyLastChar = "#"

	def __init__(self, rows, listbox=_Listbox):
		self.widgets = {"listview": listbox()}
		self.listViewList = rows
		self.beforeFilterListViewList = rows
		self["listview"].setList(rows)
		self.refresh()

	def __getitem__(self, key):
		return self.widgets.setdefault(key, _Label())

	# --- periphery the filter does not depend on ---------------------------

	def refresh(self):
		# the part of the real refresh() that matters here
		self.selection = self["listview"].getCurrent()
		if self.selection is not None and self.selection[1].get("tagType") != "Directory":
			self.handleViewStateInformation()

	def processSubViewElements(self, myType=None):
		pass

	def setLevelActive(self, currentLevel):
		self.currentFunctionLevel = str(currentLevel)

	def alterColorFunctionNames(self, level):
		pass

	def initPlayMode(self):
		pass

	def initResumeMode(self):
		pass

	def leaveNow(self):
		pass


for _name, _function in VIEW_METHODS.items():
	if _name not in FakeView.__dict__:
		setattr(FakeView, _name, _function)


class FakeMenu(object):
	"""The section menu, which filters with DPH_Filter.filter()."""

	onNumberKeyLastChar = "#"

	def __init__(self, rows, listbox=_Listbox):
		self.widgets = {"menu": listbox()}
		self.listViewList = rows
		self.beforeFilterListViewList = rows
		self["menu"].setList(rows)

	def __getitem__(self, key):
		return self.widgets.setdefault(key, _Label())

	def refreshMenu(self):
		pass


FakeMenu.filter = FILTER_METHODS["filter"]


def rows(spec):
	"""(title, viewCount) pairs -> rows shaped like the real list entries."""
	out = []
	for number, (title, viewCount) in enumerate(spec):
		entryData = {
			"title": title, "tagType": "Video", "type": "movie", "viewCount": viewCount,
			"ratingKey": str(1000 + number), "server": "server:32400", "currentViewMode": "movies",
		}
		icon = SEEN if viewCount != "0" else UNSEEN
		out.append((title, entryData, "context", icon, "/library/metadata/%d" % (1000 + number)))
	return out


LIBRARY = [
	("2 Fast 2 Furious", "0"), ("2 Francos", "0"), ("Amelie", "0"),
	("UFO Sweden", "0"), ("Umma", "1"), ("Un altre home", "0"), ("Zodiac", "0"),
]


def answer(state, viewCount):
	"""The server's reply to the pending marker refresh."""
	fresh = ("fresh", {"viewCount": viewCount}, None, state, "fresh")
	PENDING.pop()(([fresh], None), None)


class LetterFilterTest(unittest.TestCase):
	LISTBOX = _Listbox

	def setUp(self):
		del PENDING[:]

	def view(self):
		return FakeView(rows(LIBRARY), self.LISTBOX)

	def typeLetter(self, view, char):
		view.onNumberKeyLastChar = char
		view.filter()

	def filtered(self, char):
		view = self.view()
		view.initFilterMode()
		view.currentFunctionLevel = "4"
		self.typeLetter(view, char)
		return view

	def rowTitled(self, view, title):
		for row in view.listViewList:
			if row[0] == title:
				return row
		self.fail("%r is not in the list on screen" % title)

	def select(self, view, title):
		for index, row in enumerate(view["listview"].list):
			if row[0] == title:
				view["listview"].setIndex(index)
				view.refresh()
				return row
		self.fail("%r is not in the list on screen" % title)


class TestMarksSurviveClearingTheFilter(LetterFilterTest):
	def test_seen_marked_under_a_filter_survives_clearing_it(self):
		view = self.filtered("U")
		self.select(view, "UFO Sweden")

		view.markWatched()
		self.typeLetter(view, " ")

		self.assertEqual(self.rowTitled(view, "UFO Sweden")[3], SEEN,
				"clearing the filter brought the old icon back")

	def test_unseen_marked_under_a_filter_survives_clearing_it(self):
		view = self.filtered("U")
		self.select(view, "Umma")

		view.markUnwatched()
		self.typeLetter(view, " ")

		self.assertEqual(self.rowTitled(view, "Umma")[3], UNSEEN,
				"clearing the filter brought the old icon back")


class TestTheRefreshAfterPlayback(LetterFilterTest):
	def test_it_survives_clearing_the_filter(self):
		view = self.filtered("U")
		self.select(view, "UFO Sweden")

		view.refreshEntryViewState()
		answer("seen", "1")
		self.typeLetter(view, " ")

		self.assertEqual(self.rowTitled(view, "UFO Sweden")[3], SEEN,
				"the refresh after playback only reached the filtered list")

	def test_an_answer_for_a_row_filtered_out_meanwhile_lands_on_that_row_only(self):
		view = self.filtered("U")
		self.select(view, "UFO Sweden")
		view.refreshEntryViewState()

		# the filter changes before the server answers
		self.typeLetter(view, "2")
		bystander = view.listViewList[0]
		answer("seen", "1")

		self.assertIs(view.listViewList[0], bystander,
				"the answer for one row was written over another")
		self.assertEqual(bystander[1]["viewCount"], "0",
				"the answer for one row changed another row's watch state")

		self.typeLetter(view, " ")
		self.assertEqual(self.rowTitled(view, "UFO Sweden")[3], SEEN)

	def test_an_answer_after_leaving_the_level_changes_nothing(self):
		view = self.view()
		self.select(view, "UFO Sweden")
		view.refreshEntryViewState()

		# back out to another level before the server answers. It has more
		# rows than the index captured for the request: with fewer, writing
		# at that index raises, the exception is swallowed, and the test
		# passes for the wrong reason.
		other = rows([("Episode %d" % n, "0") for n in range(1, 6)])
		view.listViewList = view.beforeFilterListViewList = other
		view["listview"].setList(other)
		snapshot = list(other)
		answer("seen", "1")

		self.assertEqual([id(row) for row in other], [id(row) for row in snapshot],
				"the answer for a row of another level was written into this one")
		self.assertEqual([row[1]["viewCount"] for row in other], ["0"] * 5)

	def test_it_updates_the_yellow_label(self):
		view = self.view()
		self.select(view, "UFO Sweden")
		self.assertEqual(view["btn_yellowText"].text, "set 'Seen'")

		view.refreshEntryViewState()
		answer("seen", "1")

		self.assertEqual(view["btn_yellowText"].text, "set 'Unseen'",
				"the yellow button still offers to mark as seen a row just refreshed as seen")


class TestLeavingTheFilterMode(LetterFilterTest):
	def test_red_brings_the_whole_list_back_on_the_same_entry(self):
		view = self.filtered("U")
		chosen = self.select(view, "Un altre home")

		getattr(view, redHandlerInFilterMode())()

		self.assertFalse(view.filterMode)
		self.assertIs(view.listViewList, view.beforeFilterListViewList,
				"leaving the filter mode kept the list filtered")
		self.assertIs(view["listview"].list, view.listViewList,
				"the list on screen is not the one the player would get")
		self.assertIs(view["listview"].getCurrent(), chosen,
				"the cursor did not stay on the same entry")

	def test_after_red_the_yellow_label_matches_the_entry_under_the_cursor(self):
		view = self.filtered("U")
		self.select(view, "Umma")

		getattr(view, redHandlerInFilterMode())()

		expected = "set 'Unseen'" if view["listview"].getCurrent()[3] == SEEN else "set 'Seen'"
		self.assertEqual(view["btn_yellowText"].text, expected)

	def test_after_red_the_label_is_worked_out_again_not_left_over(self):
		# leaveFilterMode() has to work seen/unseen out again for the entry
		# under the cursor before the yellow button is painted. A cursor that
		# stays on the same entry never tells a recomputed value from one left
		# over, so start from a value left over from another entry.
		view = self.filtered("U")
		self.select(view, "UFO Sweden")
		view.seen = True  # left over from some other entry

		getattr(view, redHandlerInFilterMode())()

		self.assertEqual(view["btn_yellowText"].text, "set 'Seen'",
				"the yellow button was painted from a value left over from another entry")

	def test_ok_under_a_filter_does_not_swap_the_list_under_the_cursor(self):
		# onEnter() calls toggleFilterMode(quit=True) on every OK and reads the
		# cursor AFTER it, to pick what to play from self.listViewList. If that
		# call restored the whole list, the cursor would point into another
		# list and the player would get another entry.
		view = self.filtered("U")
		chosen = self.select(view, "Umma")
		before = view.listViewList

		view.toggleFilterMode(quit=True)

		self.assertIs(view.listViewList, before)
		self.assertIs(view["listview"].list, before)
		self.assertIs(view.listViewList[view["listview"].getIndex()], chosen)


class TestLettersThatMatchNothing(LetterFilterTest):
	def test_a_letter_nothing_starts_with_keeps_the_list(self):
		view = self.view()
		before = view.listViewList

		self.typeLetter(view, "0")

		self.assertIs(view.listViewList, before, "a letter no title starts with emptied the list")
		self.assertIs(view["listview"].list, before)

	def test_an_empty_title_does_not_break_the_filter(self):
		view = FakeView(rows([("", "0"), ("UFO Sweden", "0")]), self.LISTBOX)

		self.typeLetter(view, "U")

		self.assertEqual([row[0] for row in view.listViewList], ["UFO Sweden"])

	def test_the_section_menu_keeps_its_list_too(self):
		menu = FakeMenu([("Pel.lis",), ("Series",), ("Documentals",)], self.LISTBOX)
		before = menu.listViewList

		menu.onNumberKeyLastChar = "0"
		menu.filter()

		self.assertIs(menu.listViewList, before, "a letter no section starts with emptied the menu")
		self.assertIs(menu["menu"].list, before)

	def test_an_empty_section_name_does_not_break_the_menu_filter(self):
		menu = FakeMenu([("",), ("Series",)], self.LISTBOX)

		menu.onNumberKeyLastChar = "S"
		menu.filter()

		self.assertEqual([row[0] for row in menu.listViewList], ["Series"])


class TestTheCursorAfterFiltering(LetterFilterTest):
	"""A list filter() puts on screen starts at the top. Only the receiver's
	listbox can tell: the resetting one puts the cursor there whatever the
	code does."""

	def test_a_new_letter_starts_at_the_top(self):
		view = self.view()
		self.select(view, "Zodiac")  # deep in the list
		view.initFilterMode()
		view.currentFunctionLevel = "4"

		self.typeLetter(view, "U")

		self.assertEqual(view["listview"].getIndex(), 0,
				"the filtered list opened wherever the old index fell")

	def test_filtering_again_after_red_starts_at_the_top(self):
		# seen on the receiver: RED left the cursor deep in the whole list, and
		# filtering again landed on the last row of the new one
		view = self.filtered("U")
		self.select(view, "Un altre home")
		getattr(view, redHandlerInFilterMode())()

		view.initFilterMode()
		view.currentFunctionLevel = "4"
		self.typeLetter(view, "U")

		self.assertEqual(view["listview"].getIndex(), 0)

	def test_showing_everything_again_starts_at_the_top(self):
		view = self.filtered("U")
		self.select(view, "Un altre home")

		self.typeLetter(view, " ")

		self.assertEqual(view["listview"].getIndex(), 0)

	def test_the_section_menu_starts_at_the_top_too(self):
		menu = FakeMenu([("Documentals",), ("Pel.lis",), ("Series",), ("Series infantils",)], self.LISTBOX)
		menu["menu"].setIndex(3)

		menu.onNumberKeyLastChar = "S"
		menu.filter()

		self.assertEqual(menu["menu"].getIndex(), 0)


class TestEveryRowReplacementGoesThroughOnePlace(unittest.TestCase):
	"""A row replaced in only one of the two lists is how the old icon came
	back. Hold the invariant structurally: no method writes a row of either
	list directly; they all go through replaceListEntry()."""

	SITES = ("markWatched", "markUnwatched", "applyRefreshedViewState")

	def test_no_method_replaces_a_row_in_one_list_only(self):
		seen, direct, calls = set(), [], set()
		for func in VIEW_CLASS.body:
			if not isinstance(func, ast.FunctionDef):
				continue
			seen.add(func.name)
			for node in ast.walk(func):
				if isinstance(node, ast.Assign):
					for target in node.targets:
						if (isinstance(target, ast.Subscript)
								and isinstance(target.value, ast.Attribute)
								and target.value.attr in ("listViewList", "beforeFilterListViewList")
								and getattr(target.value.value, "id", None) == "self"):
							direct.append("%s():%d" % (func.name, node.lineno))
				if (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "replaceListEntry"):
					calls.add(func.name)

		missing = [name for name in self.SITES if name not in seen]
		self.assertEqual(missing, [], "the walk no longer finds %s - it has stopped matching" % missing)
		self.assertEqual(direct, [],
				"these replace a row in one list only (%d methods inspected):\n  %s"
				% (len(seen), "\n  ".join(direct)))
		self.assertEqual(sorted(set(self.SITES) - calls), [],
				"these no longer go through replaceListEntry()")


class OnTheReceiversListbox(object):
	"""The same cases, with the listbox the receiver really has."""
	LISTBOX = _ClampingListbox


class TestMarksSurviveClearingTheFilterOnTheReceiversListbox(OnTheReceiversListbox, TestMarksSurviveClearingTheFilter):
	pass


class TestTheRefreshAfterPlaybackOnTheReceiversListbox(OnTheReceiversListbox, TestTheRefreshAfterPlayback):
	pass


class TestLeavingTheFilterModeOnTheReceiversListbox(OnTheReceiversListbox, TestLeavingTheFilterMode):
	pass


class TestLettersThatMatchNothingOnTheReceiversListbox(OnTheReceiversListbox, TestLettersThatMatchNothing):
	pass


class TestTheCursorAfterFilteringOnTheReceiversListbox(OnTheReceiversListbox, TestTheCursorAfterFiltering):
	pass


if __name__ == "__main__":
	unittest.main()
