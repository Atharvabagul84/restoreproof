"""Loopback-only, single-worker HTTP harness; not a production HTTP server."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread

from .orders_service import OrdersError


MAX_BODY_BYTES = 1024


class OrdersHTTPServer:
    def __init__(self, service):
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(5)
                super().setup()

            def log_message(self, format, *args):
                pass

            def _send(self, status, value):
                body = json.dumps(value, allow_nan=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                lengths = self.headers.get_all("Content-Length", [])
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    raise OrdersError(400, "A single Content-Length is required.")
                try:
                    length = int(lengths[0])
                except ValueError:
                    raise OrdersError(400, "Invalid content length.") from None
                if length < 0 or length > MAX_BODY_BYTES:
                    raise OrdersError(413, "Request body exceeds the limit.")
                if self.headers.get_content_type() != "application/json":
                    raise OrdersError(400, "JSON is required.")
                try:
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("Incomplete body")
                    return json.loads(raw)
                except (ValueError, UnicodeError):
                    raise OrdersError(400, "Invalid JSON body.") from None

            def _handle(self, method):
                try:
                    if len(self.path) > 128:
                        raise OrdersError(400, "Invalid request path.")
                    auth = self.headers.get("Authorization")
                    if method == "GET" and self.path.startswith("/orders/"):
                        status, result = 200, service.get(auth, self.path[len("/orders/"):])
                    elif method == "POST" and self.path == "/orders":
                        status, result = 201, service.create(auth, self._body())
                    else:
                        raise OrdersError(404, "Route not found.")
                except OrdersError as error:
                    status, result = error.status, {"error": str(error)}
                except Exception:
                    status, result = 500, {"error": "Application operation failed."}
                self._send(status, result)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=6)
