"""Stdlib HTTPServer scaffold + Flask-style app.run, both bound wide open."""
from http.server import HTTPServer, BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


def main() -> None:
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()


# Pretend Flask import — the call shape is what the detector cares about.
class _App:
    def run(self, host: str = "127.0.0.1", port: int = 5000) -> None: ...


app = _App()


def start_flask() -> None:
    app.run(host="0.0.0.0", port=5000)
