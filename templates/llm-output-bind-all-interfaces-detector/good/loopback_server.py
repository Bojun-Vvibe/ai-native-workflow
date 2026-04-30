"""Same services, bound to loopback by default. Operators opt into wider
exposure via env, which keeps the dangerous default out of source."""
import os
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()


def serve_loopback(port: int = 9000) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.listen(5)


def serve_env(port: int = 8080) -> None:
    host = os.environ.get("BIND_HOST", "127.0.0.1")
    HTTPServer((host, port), Handler).serve_forever()


# A docstring that mentions 0.0.0.0 in prose must not trip the AST scanner.
NOTE = "Operators may set BIND_HOST=0.0.0.0 in container envs only."
