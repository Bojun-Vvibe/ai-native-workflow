"""Flask-style app.run with safe defaults — must not be flagged."""


class _App:
    def run(self, host: str = "127.0.0.1", port: int = 5000) -> None: ...


app = _App()


def start_local() -> None:
    app.run(host="127.0.0.1", port=5000)


def start_localhost_alias() -> None:
    app.run(host="localhost", port=5001)
