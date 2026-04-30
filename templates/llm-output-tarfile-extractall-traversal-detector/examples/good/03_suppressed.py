"""Good: audited and explicitly suppressed."""
import tarfile

def restore_trusted(path, dest):
    # We control the archive producer, paths are validated upstream.
    tarfile.open(path).extractall(dest)  # extractall-ok
