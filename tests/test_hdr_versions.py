# -*- coding: utf-8 -*-
"""HDR in the "Select media to play" dialog.

A box without HDR cannot show an HDR version right: a transcode that keeps
its BT.2020/HLG signalling comes out black (measured with Emby on a Zgemma
H8.2H by the DreamFin fork; whether Plex tone-maps depends on the server).
So every version now carries its HDR kind, the dialog names it, and on a box
without HDR the SDR versions come first - the dialog opens on the first
entry. The version still travels by its own mediaIndex ([7]), never by its
place in the list.

boxSupportsHdr() and the ninth field of buildMediaChoiceName() are shared
with the DreamFin fork (bb3e391, f278be2) and ported as they are, with their
tests: whether the box can output HDR, whether the user turned it off, and
whether the TV's EDID takes it.
Reading the kind is Plex's own: the video stream's colorTrc and DOVIPresent.
"""

import binascii
import os
import shutil
import tempfile
import unittest

try:
	from tests import helpers, plexmock
except ImportError:  # direct invocation from the tests directory
	import helpers
	import plexmock

helpers.setup_environment()

from src.__common__ import boxSupportsHdr, buildMediaChoiceName, edidTakesHdr  # noqa: E402
import src.DP_PlexLibrary as plexlibrary  # noqa: E402


def _edid(extensions=(), declared=None):
	"""An EDID: the base block plus one CTA-861 extension per list of data
	blocks. declared overrides the extension count the base block announces."""
	data = bytearray(128)
	data[0:8] = bytearray(b"\x00\xff\xff\xff\xff\xff\xff\x00")
	data[126] = len(extensions) if declared is None else declared
	for blocks in extensions:
		payload = bytearray()
		for block in blocks:
			payload += block
		extension = bytearray(128)
		extension[0], extension[1], extension[2] = 0x02, 0x03, 4 + len(payload)
		extension[4:4 + len(payload)] = payload
		data += extension
	return bytes(data)


VIDEO_BLOCK = bytearray([0x40 | 2, 0x10, 0x04])  # tag 2: two short video descriptors
HDR_PQ_HLG = bytearray([0xE0 | 3, 0x06, 0x0D, 0x01])  # extended tag 6: SDR + PQ + HLG
HDR_SDR_ONLY = bytearray([0xE0 | 3, 0x06, 0x01, 0x01])  # extended tag 6: SDR curve only
DOLBY_VISION = bytearray([0xE0 | 8, 0x01, 0x46, 0xD0, 0x00, 0, 0, 0, 0])  # OUI 00-D0-46
COLORIMETRY_BT2020 = bytearray([0xE0 | 3, 0x05, 0xC0, 0x00])  # extended tag 5: BT.2020 colours, which are not HDR


class TestEdidTakesHdr(unittest.TestCase):
	"""The CTA-861 blocks that say whether the TV takes HDR."""

	def test_a_tv_announcing_pq_and_hlg(self):
		self.assertTrue(edidTakesHdr(_edid([[VIDEO_BLOCK, HDR_PQ_HLG]])))

	def test_a_tv_with_dolby_vision(self):
		self.assertTrue(edidTakesHdr(_edid([[VIDEO_BLOCK, DOLBY_VISION]])))

	def test_a_tv_with_no_hdr_block(self):
		self.assertFalse(edidTakesHdr(_edid([[VIDEO_BLOCK]])))

	def test_a_tv_whose_hdr_block_lists_only_the_sdr_curve(self):
		self.assertFalse(edidTakesHdr(_edid([[VIDEO_BLOCK, HDR_SDR_ONLY]])))

	def test_an_edid_without_extensions(self):
		self.assertFalse(edidTakesHdr(_edid([])))

	def test_a_cut_edid_cannot_tell(self):
		self.assertIsNone(edidTakesHdr(_edid([], declared=1)))

	def test_something_else_cannot_tell(self):
		self.assertIsNone(edidTakesHdr(b"not an edid"))
		self.assertIsNone(edidTakesHdr(b""))

	def test_amlogic_hands_it_over_as_hex_text(self):
		text = binascii.hexlify(_edid([[VIDEO_BLOCK, HDR_PQ_HLG]])) + b"\n"
		self.assertTrue(edidTakesHdr(text))


SF8008_VIDEO_MODES = ("pal ntsc 480i 480p 576i 576p 720p50 720p 720p24 1080i50 1080i 1080p50 1080p 1080p24 "
		"2160p25 2160p30 2160p50 2160p 2160p24")  # its videomode_choices, as read on the box


class TestBoxSupportsHdr(unittest.TestCase):
	"""The same files OpenATV 7.0 and 8.0 look at (Components/AVSwitch), the
	settings the box obeys, and the TV's EDID."""

	def setUp(self):
		self.root = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.root)

	def touch(self, path, content=""):
		full = self.root + path
		if not os.path.isdir(os.path.dirname(full)):
			os.makedirs(os.path.dirname(full))
		# always binary: py2 in text mode would turn an EDID's \n bytes into \r\n on Windows
		data = content if isinstance(content, bytes) else content.encode("utf-8")
		with open(full, "wb") as handle:
			handle.write(data)

	def a_4k_hisilicon_box(self, hdrType="auto"):
		self.touch("/proc/stb/video/videomode_choices", "720p 1080i 1080p 2160p24 2160p25 2160p50 2160p")
		self.touch("/proc/stb/video/hdmi_hdrtype", hdrType)
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "none auto dolby hdr10 hlg")

	def a_4k_broadcom_box(self, hlg="auto(EDID)", hdr10="auto(EDID)"):
		self.touch("/proc/stb/video/videomode_choices", "720p 1080i 1080p 2160p30 2160p")
		self.touch("/proc/stb/hdmi/hlg_support_choices", "auto(EDID) yes no")
		self.touch("/proc/stb/hdmi/hlg_support", hlg)
		self.touch("/proc/stb/hdmi/hdr10_support", hdr10)

	def test_the_user_set_the_hisilicon_hdr_type_to_sdr(self):
		self.a_4k_hisilicon_box(hdrType="none")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_the_user_turned_off_both_broadcom_hdr_kinds(self):
		self.a_4k_broadcom_box(hlg="no", hdr10="no")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_one_broadcom_hdr_kind_still_on(self):
		self.a_4k_broadcom_box(hlg="no", hdr10="auto(EDID)")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_a_4k_box_with_an_sdr_tv(self):
		self.a_4k_hisilicon_box()
		self.touch("/proc/stb/hdmi/raw_edid", _edid([[VIDEO_BLOCK]]))
		self.assertFalse(boxSupportsHdr(self.root))

	def test_a_4k_box_with_an_hdr_tv(self):
		self.a_4k_hisilicon_box()
		self.touch("/proc/stb/hdmi/raw_edid", _edid([[VIDEO_BLOCK, HDR_PQ_HLG]]))
		self.assertTrue(boxSupportsHdr(self.root))

	def test_a_4k_box_whose_tv_cannot_be_read(self):
		self.a_4k_hisilicon_box()
		self.touch("/proc/stb/hdmi/raw_edid", _edid([], declared=1))
		self.assertTrue(boxSupportsHdr(self.root))

	def test_an_amlogic_box_with_an_sdr_tv(self):
		self.touch("/proc/stb/video/videomode_choices", "1080p 2160p")
		self.touch("/sys/class/amhdmitx/amhdmitx0/config", "")
		self.touch("/sys/class/amhdmitx/amhdmitx0/rawedid", binascii.hexlify(_edid([[VIDEO_BLOCK]])))
		self.assertFalse(boxSupportsHdr(self.root))

	def test_a_box_with_none_of_them_has_no_hdr(self):
		self.assertFalse(boxSupportsHdr(self.root))

	def test_broadcom(self):
		self.touch("/proc/stb/hdmi/hlg_support_choices", "auto yes no")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_amlogic(self):
		self.touch("/sys/class/amhdmitx/amhdmitx0/config")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_hisilicon_offering_hdr(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr hdr10 hlg")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_hisilicon_offering_only_sdr(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_hisilicon_without_its_choices(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.assertTrue(boxSupportsHdr(self.root))

	def test_a_1080p_box_whose_driver_lists_hdr_types_has_no_hdr(self):
		"""The Zgemma H8.2H as read on the box (hi3716mv430, 2026-10-05)."""
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "none auto autofirstframe dolby hdr10 hlg")
		self.touch("/proc/stb/video/videomode_choices",
				"pal ntsc 720p 720p50 1080i 1080i50 1080p24 1080p25 1080p30 1080p50 1080p 576i 576p 480i 480p")
		self.assertFalse(boxSupportsHdr(self.root))

	def test_a_4k_box_with_hdr_types(self):
		self.touch("/proc/stb/video/hdmi_hdrtype", "auto")
		self.touch("/proc/stb/video/hdmi_hdrtype_choices", "auto sdr hdr10 hlg")
		self.touch("/proc/stb/video/videomode_choices", "720p 1080i 1080p 2160p24 2160p25 2160p50 2160p")
		self.assertTrue(boxSupportsHdr(self.root))

	def the_sf8008_on_openatv_7_0(self, hdrType="auto"):
		"""The Octagon SF8008 as read on the box (HiSilicon, OpenATV 7.0,
		2026-10-05): hdmi_hdrtype without its choices, and no Broadcom or Amlogic
		files, so only the last test of _boxCanOutputHdr says it can do HDR. The
		monitors' EDIDs below have the structure measured on it, with made-up
		bytes (the real ones carry the screen's model and serial number)."""
		self.touch("/proc/stb/video/videomode_choices", SF8008_VIDEO_MODES)
		self.touch("/proc/stb/video/hdmi_hdrtype", hdrType)

	def test_the_sf8008_with_an_hdr_monitor(self):
		self.the_sf8008_on_openatv_7_0()
		self.touch("/proc/stb/hdmi/raw_edid", _edid([[VIDEO_BLOCK, HDR_PQ_HLG]]))
		self.assertTrue(boxSupportsHdr(self.root))

	def test_the_sf8008_with_a_monitor_without_hdr(self):
		self.the_sf8008_on_openatv_7_0()
		self.touch("/proc/stb/hdmi/raw_edid", _edid([[VIDEO_BLOCK, COLORIMETRY_BT2020]]))
		self.assertFalse(boxSupportsHdr(self.root))

	def test_the_sf8008_with_its_hdr_type_set_to_sdr(self):
		self.the_sf8008_on_openatv_7_0(hdrType="none")
		self.touch("/proc/stb/hdmi/raw_edid", _edid([[VIDEO_BLOCK, HDR_PQ_HLG]]))
		self.assertFalse(boxSupportsHdr(self.root))

	def test_the_sf8008_with_no_screen_to_read(self):
		"""With no screen whose EDID is valid, raw_edid is there but reading it
		fails: the TV cannot be told, so what the box can do stands."""
		self.the_sf8008_on_openatv_7_0()
		os.makedirs(self.root + "/proc/stb/hdmi/raw_edid")  # opening a directory fails like the driver does
		self.assertTrue(boxSupportsHdr(self.root))


class TestTheDialogNamesTheKind(unittest.TestCase):
	def test_the_hdr_kind_goes_into_the_prefix(self):
		items = ("/library/parts/3301/1/file.mkv", "/data/movies/Movie.2160p.mkv",
				"mkv", "4710000000", "6792", "4K", "hevc", 0, "HLG")

		self.assertEqual(buildMediaChoiceName(items),
				"[4K / hevc / HLG / 4.39 GB]  Movie.2160p.mkv")

	def test_an_sdr_version_says_nothing_about_it(self):
		items = ("/library/parts/3302/1/file.mkv", "/data/movies/Movie.1080p.mkv",
				"mkv", "1073741824", "6792", "1080", "hevc", 1, "")

		self.assertEqual(buildMediaChoiceName(items),
				"[1080 / hevc / 1.0 GB]  Movie.1080p.mkv")

	def test_eight_fields_still_work(self):
		items = ("/library/parts/3302/1/file.mkv", "/data/movies/Movie.1080p.mkv",
				"mkv", "1073741824", "6792", "1080", "hevc", 1)

		self.assertEqual(buildMediaChoiceName(items),
				"[1080 / hevc / 1.0 GB]  Movie.1080p.mkv")


class TestPlexVersions(unittest.TestCase):
	"""Four versions on the mock PMS: 4K HLG, 1080p SDR, 4K Dolby Vision and
	4K HDR10, in that order (mediaIndex 0-3)."""

	def setUp(self):
		self.mock = plexmock.MockPMS().start()
		self.addCleanup(self.mock.stop)
		self.mock.add_xml("/library/metadata/1005", helpers.fixture("metadata_hdr_versions.xml"))
		self.addCleanup(setattr, plexlibrary, "boxSupportsHdr", plexlibrary.boxSupportsHdr)

	def options(self, ratingKey="1005", hdr=None, loadExtraData=False):
		if hdr is None:
			def unexpected():
				raise AssertionError("boxSupportsHdr() asked although nothing needs reordering")
			plexlibrary.boxSupportsHdr = unexpected
		else:
			plexlibrary.boxSupportsHdr = lambda: hdr
		plex = helpers.make_plex_instance(mock=self.mock)
		count, options, server = plex.getMediaOptionsToPlay(
			ratingKey, "http://%s/library/sections/1/all" % self.mock.address, False,
			myType="Video", loadExtraData=loadExtraData)
		return options

	def test_each_version_carries_its_kind(self):
		options = self.options(hdr=True)

		self.assertEqual(dict((o[7], o[8]) for o in options), {0: "HLG", 1: "", 2: "DV", 3: "HDR10"})

	def test_a_box_with_hdr_keeps_the_servers_order(self):
		self.assertEqual([o[7] for o in self.options(hdr=True)], [0, 1, 2, 3])

	def test_a_box_without_hdr_gets_sdr_first(self):
		# stable: the HDR versions keep their relative order behind it
		self.assertEqual([o[7] for o in self.options(hdr=False)], [1, 0, 2, 3])

	def test_the_chosen_version_still_travels_by_its_own_index(self):
		options = self.options(hdr=False)

		# what DP_Player.setSelectedMedia() does with the dialog's first entry
		chosen = options[0]
		self.assertTrue(chosen[0].endswith("file-sdr.mkv"))
		self.assertEqual(chosen[7], 1)

	def test_the_dialog_label_names_the_kind(self):
		labels = [buildMediaChoiceName(o) for o in self.options(hdr=True)]

		self.assertTrue(labels[0].startswith("[4k / hevc / HLG / "), labels[0])
		self.assertTrue(labels[1].startswith("[1080 / h264 / "), labels[1])
		self.assertTrue(labels[2].startswith("[4k / hevc / DV / "), labels[2])

	def test_a_list_that_does_not_mix_ranges_never_asks_the_box(self):
		# both versions SDR as far as Plex says (no colorTrc on either)
		self.mock.add_xml("/library/metadata/1002", helpers.fixture("metadata_multiversion.xml"))

		options = self.options(ratingKey="1002")

		self.assertEqual([o[7] for o in options], [0, 1])

	def test_extras_are_left_alone(self):
		self.mock.add_xml("/library/metadata/1003", helpers.fixture("metadata_trailer_extras.xml"))

		options = self.options(ratingKey="1003", loadExtraData=True)

		self.assertEqual(len(options), 1)
		self.assertEqual(len(options[0]), 6)


if __name__ == "__main__":
	unittest.main()
