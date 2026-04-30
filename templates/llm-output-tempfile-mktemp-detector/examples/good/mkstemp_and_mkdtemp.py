import os
import tempfile


def write_payload(data: bytes) -> str:
    fd, path = tempfile.mkstemp(suffix=".bin")
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def staging_dir() -> str:
    return tempfile.mkdtemp(prefix="job-")
