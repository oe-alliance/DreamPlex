# DreamPlex

**Media server client for Enigma2 set-top boxes.**

Browse your movie, TV show and music libraries straight from the box and play
them on the television, with posters, backdrops and metadata.

![License](https://img.shields.io/badge/license-GPL--2.0--or--later-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/platform-Enigma2-lightgrey)

🇮🇹 *Questo documento è disponibile anche [in italiano](README.it.md).*

---

## Supported servers

| Server | Network discovery | Authentication |
|---|---|---|
| **Plex** | GDM (multicast) | local, or plex.tv account with Home Users |
| **Jellyfin** | HTTP subnet scan | username and password, or API key |

The two coexist: you can configure several servers of either kind and switch
between them from the menu.

## Features

**Libraries and navigation**
- Movies, TV shows, music and mixed sections
- Several selectable views (list, long list, backdrop list), with a default
  view configurable per library type
- Filters by genre, year, rating and duration, plus free-text search
- Seen / unseen counts for TV shows
- Local cache of server responses for faster browsing

**Playback**
- Direct play, direct local play (through mapped network paths) or
  transcoded playback, with selectable quality profiles
- Resume where you left off, with progress reported back to the server
- Audio and subtitle track selection, preferred languages and forced
  subtitle support
- **Next episode prompt**: towards the end of an episode a panel with a
  countdown appears in the bottom right corner. `OK` plays the next episode
  straight away, `EXIT` dismisses it, and if you do nothing playback moves on
  when the countdown expires. Both the threshold and the countdown are
  configurable.

**Offline content**
- Syncs posters and backdrops to the box storage
- Renders backdrops as background videos in the views

**Other**
- Multiple users with PIN protection
- Wake on Lan, to start the server before connecting
- Remote player: drive playback from a compatible app
- User interface translated into 8 languages

## Installation

The package is architecture independent: the same `.ipk` works on Zgemma,
Vu+ and other Enigma2 boxes.

```
opkg install ./dreamplex_*_all.ipk
```

After installation the plugin appears among the extensions. On first run add a
server from the **Server** menu, either through automatic discovery or by
entering address and port by hand.

### Requirements

- Enigma2 image with **Python 3.8 or newer**
- Required package: `python3-six`

These are optional, each needed by a single feature. The plugin starts and
works without them, and tells you when one is missing:

| Package | Needed for |
|---|---|
| `gstreamer1.0-plugins-bad-fragmented` | transcoded playback |
| `python3-pillow`, `mjpegtools` | rendering backdrops as videos |

## Building from source

```
autoreconf -i
./configure --prefix=/usr
make
make DESTDIR=/path/to/staging install
```

There are no native components to compile: the plugin is pure Python, and the
only build step is compiling the translation catalogues (`.po` → `.mo`), which
are architecture independent.

## Skins

Big thanks to the skinners :-)

- **Blockbuster** — [vuplus-support.org](http://www.vuplus-support.org/wbb3/index.php?page=Thread&threadID=69568&s=e395351f57ca026d487fb76176f04b75bbb59c0f)
- **YouPlex** (Blue, Green, Purple, Red) — [OpenViX/DreamPlexSkins](https://github.com/OpenViX/DreamPlexSkins)
- **Plex_Experience** — [OpenViX/DreamPlexSkins](https://github.com/OpenViX/DreamPlexSkins)

The plugin ships the `default`, `default_FHD`, `BlueMod`, `BlueMod_FHD`,
`Carousel` and `Carousel_FHD` skins, available in 720p and 1080p.

`Carousel` is a vertical-sidebar take on the main and server menus: menu
items get a number-key shortcut (1-9), and the server menu shows a rotating
"hero" banner (poster, plot, a countdown to the next suggestion) that plays
directly with OK or the blue key. Suggestions mix in-progress/next-up
("Continue watching") with recently-added titles ("Suggested"), each
labeled; picking a whole show opens its season/episode browser instead of
playing it. The rotation interval, how many loops before it re-fetches its
suggestion list, and the maximum number of suggestions requested are all
configurable in Settings (0 rotation interval disables rotation). On the
server picker (no server chosen yet), a contextual hint next to the
DreamPlex banner explains what each menu row does.

## Translations

Czech, Danish, German, English, British English, Spanish, French and Italian.
The catalogues live in [`po/`](po/): to contribute, update the file for your
language and open a pull request.

## License

GNU General Public License, version 2 or later. See
[`src/LICENSE.txt`](src/LICENSE.txt).

## Credits

Created by **DonDavici** (2012) and **jbleyel** (2021), with code taken from
other plugins: all credits to their authors.

Original project: [oe-alliance/DreamPlex](https://github.com/oe-alliance/DreamPlex)
