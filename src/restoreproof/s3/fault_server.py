"""A loopback-only lab fault: close HTTP before the promised object completes."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from .client import create_client


@contextmanager
def interrupted_download(version_id, length):
    class InterruptedObject(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', str(length))
            self.send_header('x-amz-version-id', version_id)
            self.end_headers()
            self.wfile.write(b'PGDMPcut')
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), InterruptedObject)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = create_client(endpoint=f'http://127.0.0.1:{server.server_port}')
    try:
        yield client
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError('Fault server did not stop.')
