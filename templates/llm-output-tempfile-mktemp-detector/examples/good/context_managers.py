import tempfile


def write_payload(data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=True) as fh:
        fh.write(data)
        fh.flush()
        fh.seek(0)
        return fh.read()


def workdir_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as d:
        # Use d for scratch work; auto-cleaned on exit.
        _ = d
