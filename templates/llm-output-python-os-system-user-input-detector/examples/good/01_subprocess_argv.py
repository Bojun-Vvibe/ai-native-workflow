# Good: argv-list subprocess.run is the safe replacement.
import subprocess


def ping(host: str) -> int:
    return subprocess.run(
        ["ping", "-c", "1", "--", host],
        check=False,
        timeout=5,
    ).returncode
