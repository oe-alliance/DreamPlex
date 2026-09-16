# -*- coding: utf-8 -*-
"""
Jellyfin discovery through HTTP probing on the local network.

Queries /System/Info/Public on port 8096 for the hosts of the subnet and
builds a list of DiscoveredServer.

The scan must never run on the enigma2 main loop: a /24 with a half second
timeout per host would take up to two minutes, during which the box would be
completely frozen. start_discovery() therefore works in a separate thread and
probes the hosts in parallel; the caller follows its progress with an eTimer
and only reads the results once discovery_complete is set. The API mirrors the
one of DPH_PlexGdm, so that the two discoveries are interchangeable from the
user interface point of view.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen, Request

from .__common__ import printl2 as printl, getMyIp, DiscoveredServer
from .jellyfin.JellyfinSettings import JellyfinSettings

# Default HTTP port of Jellyfin.
JELLYFIN_HTTP_PORT = 8096

# Number of hosts probed in parallel. A full /24 completes in a few seconds
# without exhausting the connections available on the box.
MAX_PARALLEL_PROBES = 32


class JellyfinDiscovery(object):
	def __init__(self, timeout=0.5):
		self.timeout = timeout
		self.server_list: list[DiscoveredServer] = []
		self.discovery_complete = False
		self._custom_base = None  # e.g. "192.168.1"
		self._custom_range = (1, 254)
		self.port = JELLYFIN_HTTP_PORT

		self._discovery_is_running = False
		self._abort = threading.Event()
		self._lock = threading.Lock()
		self._scanned = 0
		self._total = 0
		self.discover_t = None

	#===========================================================================
	#
	#===========================================================================
	def _subnet_hosts(self) -> list[str]:
		try:
			start, end = self._custom_range
			if self._custom_base:
				base = self._custom_base
			else:
				ip = getMyIp()
				if not ip or ip is False:
					return []
				base = '.'.join(ip.split('.')[:3])
			return [f"{base}.{i}" for i in range(start, end + 1)]
		except Exception as ex:
			printl("exception: " + str(ex), self, "W")
			return []

	#===========================================================================
	#
	#===========================================================================
	def set_params(self, subnet_base: str | None = None, start: int = 1, end: int = 254, timeout: float | None = None, port: int | None = None):
		if subnet_base:
			# normalize the base without the last octet
			try:
				parts = subnet_base.strip().split('.')
				if len(parts) == 4:
					parts = parts[:3]
				self._custom_base = '.'.join(parts)
			except Exception:
				self._custom_base = subnet_base
		try:
			first, last = max(1, int(start)), min(254, int(end))
			self._custom_range = (first, last) if first <= last else (last, first)
		except Exception:
			self._custom_range = (1, 254)
		if timeout is not None:
			try:
				self.timeout = float(timeout)
			except Exception:
				pass
		if port is not None:
			try:
				self.port = int(port)
			except Exception:
				pass

	#===========================================================================
	#
	#===========================================================================
	def _probe(self, host: str) -> DiscoveredServer | None:
		"""Query a single host. Returns None if it is not a Jellyfin server."""
		if self._abort.is_set():
			return None
		try:
			url = f"http://{host}:{self.port}/System/Info/Public"
			req = Request(url, headers={'Accept': 'application/json'})
			with urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - http scheme fixed above
				body = resp.read().decode('utf-8')
			info = json.loads(body)
			# Expected: { 'ServerName': ..., 'Version': ..., 'ProductName': 'Jellyfin Server', 'Id': ... }
			# Id is the only field Jellyfin always fills in: without it we are
			# talking to some other service listening on the same port.
			if not isinstance(info, dict) or not info.get('Id'):
				return None
			ds = DiscoveredServer(type=JellyfinSettings.SETTINGS_NAME)
			ds.serverName = info.get('ServerName') or 'Jellyfin'
			ds.server = host
			ds.port = self.port
			ds.uuid = info.get('Id')
			ds.version = info.get('Version')
			ds.discovery = 'auto'
			return ds
		except Exception:
			# host unreachable, nothing listening, or the answer is not JSON
			return None
		finally:
			with self._lock:
				self._scanned += 1

	#===========================================================================
	#
	#===========================================================================
	def discover(self):
		"""Full scan. Blocking: only call it from a worker thread."""
		printl("", self, "S")

		hosts = self._subnet_hosts()
		with self._lock:
			self._scanned = 0
			self._total = len(hosts)

		servers: list[DiscoveredServer] = []
		if hosts:
			try:
				with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_PROBES, len(hosts))) as pool:
					for result in pool.map(self._probe, hosts):
						if result is not None:
							servers.append(result)
			except Exception as ex:
				printl("exception: " + str(ex), self, "W")

		self.server_list = servers
		self.discovery_complete = True
		printl("found: " + str(len(servers)), self, "D")
		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def start_discovery(self, daemon=True):
		printl("", self, "S")

		if self._discovery_is_running:
			printl("Discovery already running", self, "D")
			printl("", self, "C")
			return

		self._discovery_is_running = True
		self.discovery_complete = False
		self._abort.clear()
		self.server_list = []

		self.discover_t = threading.Thread(target=self._run_discovery)
		self.discover_t.daemon = daemon
		self.discover_t.start()

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def _run_discovery(self):
		try:
			self.discover()
		except Exception as ex:
			printl("exception: " + str(ex), self, "W")
			# without this the caller would wait forever
			self.discovery_complete = True
		finally:
			self._discovery_is_running = False

	#===========================================================================
	#
	#===========================================================================
	def stop_discovery(self):
		printl("", self, "S")

		self._abort.set()
		thread = self.discover_t
		if thread is not None and thread.is_alive():
			# probes already started expire within the configured timeout
			thread.join(timeout=max(2.0, self.timeout * 2))
		self._discovery_is_running = False

		printl("", self, "C")

	#===========================================================================
	#
	#===========================================================================
	def getProgress(self) -> tuple[int, int]:
		"""(hosts probed, hosts total), for the progress indication."""
		with self._lock:
			return self._scanned, self._total

	#===========================================================================
	#
	#===========================================================================
	def getServerList(self) -> list[DiscoveredServer]:
		return self.server_list
