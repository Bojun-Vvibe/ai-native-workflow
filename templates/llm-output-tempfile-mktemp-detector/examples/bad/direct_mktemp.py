import tempfile


def write_payload(data: bytes) -> str:
    path = tempfile.mktemp(suffix=".bin")
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def temp_log_path() -> str:
    return tempfile.mktemp(prefix="job-", suffix=".log")
