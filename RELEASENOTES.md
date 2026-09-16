# Release notes

🇮🇹 *Queste note sono disponibili anche [in italiano](RELEASENOTES.it.md).*

---

## 3.1.1

### 🐛 Fixed

- Jellyfin 12.0 servers rejected every request with "401 unauthorized" -
  browsing, images and direct playback all relied on authentication methods
  (`X-Emby-Authorization`, `X-MediaBrowser-Token`, `?api_key=`) that 12.0
  removed entirely. Switched to the modern `Authorization: MediaBrowser
  ...` header everywhere, including a custom-header workaround for direct
  playback URLs handed straight to the native player. Also works unchanged
  against any Jellyfin server from 10.8 on.

---

## 3.1.0

### ✨ New

- Jellyfin support: network discovery, authentication (username/password or
  API key), quality profiles, immediate audio/subtitle track override
- Unified XML configuration for all settings and servers, replacing the
  previous three separate storage locations
- Next episode prompt with a configurable countdown, in the style of the
  major streaming apps
- New optional "Carousel" skin (HD and FHD): vertical sidebar menu with
  number-key shortcuts, and a rotating "hero" banner on the server menu -
  poster, plot, a countdown to the next suggestion, playable with OK or the
  blue key
- The hero banner now mixes "Continue watching" (in-progress/next-up) with
  "Suggested" (recently added) titles, each labeled; a whole show suggested
  this way opens its season/episode browser instead of doing nothing, and
  the number of suggestions requested is configurable
- Cast/director/rating detail panel (EPG key), previously only available
  during playback, now also available while browsing
- A second key (LIST, PVR, ARCHIVE, MEDIA or FILE, whichever the remote
  actually sends) also opens the Help screen, for remotes whose HELP button
  does not reach the box as KEY_HELP
- "Refresh library" (yellow, browsing screens) is now a single, predictable
  action - always a full refresh, including posters/backdrops, with an
  on-screen "Updating..." indicator

### ⬆️ Upgrading from 3.0

- The existing configuration migrates automatically on first start - servers,
  global settings, Home Users, path mappings; nothing to re-enter
- Installing over the previous version clears the cache and downloaded media
  (posters/backdrops need re-syncing); back up first if in doubt:
  `tar czf /tmp/dreamplex-backup.tar.gz /hdd/dreamplex /etc/enigma2/settings`
- Replaces the official feed's split packages automatically

### 🐛 Fixed

- The plugin failed to start outright, in several different ways depending on
  the image: a self-import loop, two Python 2 leftovers, a crash from logging
  too early, an `UnboundLocalError` in Jellyfin's settings, and a Twisted
  import that collided with enigma2's own reactor
- A newly created server was never actually saved, and cancelling one crashed
  instead of discarding it
- Autoplay skipped the last episode of a list, and never started with only
  two episodes
- The plugin wouldn't compile at all due to a stray indentation error
- Assorted `NameError`/`ModuleNotFoundError` crashes from Python 2 leftovers
- A server could be saved unintentionally right after a successful remote
  login, even when dismissing the following confirmation with Cancel/Exit
  instead of actually confirming
- The remote's STOP key (closes the plugin), and the server menu's
  sync/cache and switch-user buttons, worked but were never shown on screen
  or in the Help legend - in some skins the switch-user button was missing
  entirely
- Changing the skin used to require a full GUI restart; now leaving and
  re-entering the plugin is enough, with an on-screen reminder after saving
- Jellyfin poster/backdrop images could silently fail to download for
  content never cached before
- Switching skins from Settings only ever offered "default" - every other
  installed skin was silently ignored
- The listing cache was written but never actually read back - every screen
  change re-fetched from the server; now a recently-viewed folder loads
  instantly, with a 5-minute freshness window
- "Refresh library" crashed on Jellyfin (it only ever asked the server to
  rescan on Plex); Jellyfin now gets the same real request
- "Delete cache" (Settings) only ever cleared the listing cache, never
  downloaded posters/backdrops - the only way to force one to re-download
  used to be deleting it by hand
- The Help key did nothing at all on the server picker, server menu and
  browsing screens - the descriptions were there, but nothing ever opened
  the Help screen on those three
- A whole TV show suggested by the hero banner (as opposed to a single
  episode) silently did nothing, or crashed the season browser if opened
  through it
- Metadata (year, cast, genre...) could randomly stay hidden for a movie row
  in a mixed folder view until a different row was visited first
- Several on-screen labels were never translated ("set 'Seen'", "fastScroll
  'On/Off'", "playback mode '...'") or actively wrong ("Runtime:" showed as
  "current status" in Italian)
- Jellyfin never auto-selected a forced embedded subtitle track the way Plex
  does
- Low-contrast/invisible text and highlights in the Carousel skin (a wrong
  assumption about how Enigma2 handles color transparency)
- Wake on Lan is now available for Jellyfin too, not just Plex; the offline
  message no longer says "Plexserver" regardless of which backend is used
- Catalog Download could silently fetch posters/backdrops without an
  authentication header on a directly-reachable Jellyfin server, and crashed
  if the header was ever actually attached
- The "prefer forced subtitles" player setting was never actually read
- A couple of on-screen strings referenced "Plex" even when configuring a
  Jellyfin server

### 🔒 Security

- Certificate verification restored for the plex.tv connections
- Backdrop rendering no longer runs through a shell
- Cache files are rejected unless written by the plugin itself

### ⚡ Responsiveness

- Jellyfin and Plex discovery no longer freeze the box while scanning the
  network
- The Wake on Lan wait no longer blocks the interface

### 🔧 Under the hood

- Python compatibility from 3.8 to 3.14
- Packaging fixes: missing subpackages, trimmed dependencies, no more stale
  bytecode shipped or left behind by upgrades
- Bare `except:` clauses replaced throughout
- Added static analysis config and a few regression-test scripts
- A handful of dead, unimplemented remote-control key handlers removed
- Server reachability testing and Wake on Lan settings are now declared on
  the shared server-settings interface, so a future backend can no longer
  silently skip them

### 🌍 Translations

- Jellyfin strings are now extracted and translatable
- Catalogue grows to 568 strings; Italian is complete

---

## 1.06
- fixed #56: theme stops playing on leave

## 1.05
- fixed direct play location check for windows server
- added some code to prevent misconfiguration in direct play ( slashes and backslashes)
- fixed order (plex defaults are untouched now :-)
- fixed newest and recently added in tv shows
- fixed gs when option live tv is enabled
- fixed streamed mode (buffer drained)
- fixed update function
- fixed media selection if more than one version is available
- fixed yellow button toggle name direct local mode
- added font details to xml for skinners
- several clean ups

## 1.04a (bugfix release)
- fixed gs in tvshow section

## 1.04
- fixed direct local with UNC path
- fixed direct local for plex on windows
- new choicebox if there is more than one version of the media in plex
- new function show location of file => menu key
- new views (long list and backdroplist) thx to tobi79ac for skinning :-) => blue key
- complete new mapping handler for direct local
- new show seen/unseen count for tvshows
- several bugfixes
- new update location => bintray

## 1.03
- UI tweaks
- added Help
- added About
- fixed when live tv stop is disabled

## 1.02
- added update function
- fixed naviagtion in tvshows
- removed buffer settings (didnt work)
- fixed quality issue playback mode "transcoded"
- options show up only when needed according to other options
- direct local mode is now also available for plex on windows
- added logrotator to have log even after greenscreen
- several bugfixes and tweaks

## 1.01
- added fastScroll feature
- fixed onDeck and recentlyViewed in TvShows
- added option: stop live tv on startup
- added option: summerize Sections
- impletmented media menu
- new feature media menu => mark as watched, unwachted and refresh library section
- small skin tweaks
- little bugfixes

## 1.00
- new hd skin (big thx to IPMAN)
- removed sd and xd skin for now
- tons of bugfixes
- another tons of bugfixes
