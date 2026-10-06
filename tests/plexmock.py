# -*- coding: utf-8 -*-
"""Tiny in-process mock of a Plex Media Server for offline tests.

Serves canned responses per path, records every request (method, path,
query, headers) and supports paginated containers (honouring the
``X-Plex-Container-Start``/``X-Plex-Container-Size`` request headers or
query parameters) plus HTTP redirects.

Works on Python 2.7 and Python 3.x.
"""

import threading

try:
	from http.server import BaseHTTPRequestHandler, HTTPServer
	from socketserver import ThreadingMixIn
except ImportError:  # Python 2
	from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
	from SocketServer import ThreadingMixIn

try:
	from urllib.parse import urlparse, parse_qs
except ImportError:  # Python 2
	from urlparse import urlparse, parse_qs


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
	# keep-alive clients (DreamPlex never closes its HTTPConnections) must
	# not block other connections, so serve each connection in a thread
	daemon_threads = True
	allow_reuse_address = True

	def handle_error(self, request, client_address):
		# clients close keep-alive connections abruptly; the resulting
		# broken pipe is expected and would only spam py2's default handler
		pass


class _Handler(BaseHTTPRequestHandler):
	protocol_version = "HTTP/1.1"

	def log_message(self, fmt, *args):  # silence the default stderr logging
		pass

	def do_GET(self):
		self._serve("GET")

	def do_POST(self):
		self._serve("POST")

	def do_PUT(self):
		self._serve("PUT")

	def do_DELETE(self):
		self._serve("DELETE")

	def _serve(self, method):
		parsed = urlparse(self.path)
		headers = {}
		for key in self.headers.keys():
			headers[key.lower()] = self.headers[key]

		record = {
			"method": method,
			"path": parsed.path,
			"query": parse_qs(parsed.query),
			"raw": self.path,
			"headers": headers,
		}
		self.server.requests.append(record)

		route = self.server.routes.get(parsed.path)
		if route is None:
			self._respond(404, "text/plain", b"not found")
			return

		rtype = route["type"]
		if rtype == "xml":
			self._respond(200, "text/xml;charset=utf-8", _encode(route["body"]))

		elif rtype == "raw":
			self._respond(200, route["content_type"], _encode(route["body"]))

		elif rtype == "redirect":
			body = b"moved"
			self.send_response(route["status"])
			self.send_header("Location", route["location"])
			self.send_header("Content-Length", str(len(body)))
			self.end_headers()
			self.wfile.write(body)

		elif rtype == "paged":
			self._respond_paged(route, record)

		elif rtype == "error":
			self._respond(route["status"], "text/plain", _encode(route.get("body", "error")))

		else:
			self._respond(500, "text/plain", b"bad route")

	def _respond_paged(self, route, record):
		items = route["items"]
		total = len(items)

		start = _container_value(record, "x-plex-container-start")
		size = _container_value(record, "x-plex-container-size")
		if start is None:
			start = 0
		if size is None:
			size = total

		window = items[start:start + size]
		attrs = dict(route.get("attrs", {}))
		attrs["size"] = str(len(window))
		attrs["totalSize"] = str(total)
		attrs["offset"] = str(start)
		attrString = " ".join('%s="%s"' % (k, v) for k, v in sorted(attrs.items()))
		body = "<MediaContainer %s>\n%s\n</MediaContainer>" % (attrString, "\n".join(window))
		self._respond(200, "text/xml;charset=utf-8", _encode(body))

	def _respond(self, status, content_type, body):
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)


def _encode(body):
	if isinstance(body, bytes):
		return body
	return body.encode("utf-8")


def _container_value(record, headerName):
	value = record["headers"].get(headerName)
	if value is None:
		# fall back to the equivalent query parameter
		values = record["query"].get("X-Plex-Container-Start" if "start" in headerName else "X-Plex-Container-Size")
		if values:
			value = values[0]
	if value is None:
		return None
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


class MockPMS(object):
	"""Mock Plex server bound to 127.0.0.1 on an ephemeral port."""

	def __init__(self):
		self.httpd = _ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
		self.httpd.routes = {}
		self.httpd.requests = []
		self.port = self.httpd.server_address[1]
		self.host = "127.0.0.1"
		self._thread = threading.Thread(target=self.httpd.serve_forever)
		self._thread.daemon = True

	# -- lifecycle ---------------------------------------------------------
	def start(self):
		self._thread.start()
		return self

	def stop(self):
		self.httpd.shutdown()
		self.httpd.server_close()

	# -- route registration -------------------------------------------------
	def add_xml(self, path, body):
		self.httpd.routes[path] = {"type": "xml", "body": body}

	def add_raw(self, path, content_type, body):
		self.httpd.routes[path] = {"type": "raw", "content_type": content_type, "body": body}

	def add_redirect(self, path, location, status=302):
		self.httpd.routes[path] = {"type": "redirect", "status": status, "location": location}

	def add_paged(self, path, items, attrs=None):
		self.httpd.routes[path] = {"type": "paged", "items": list(items), "attrs": attrs or {}}

	def add_error(self, path, status, body="error"):
		self.httpd.routes[path] = {"type": "error", "status": status, "body": body}

	# -- inspection ----------------------------------------------------------
	@property
	def address(self):
		return "%s:%d" % (self.host, self.port)

	@property
	def requests(self):
		return self.httpd.requests

	def requests_for(self, path):
		return [r for r in self.httpd.requests if r["path"] == path]

	def reset_requests(self):
		del self.httpd.requests[:]
