"""Good: tarfile with explicit safe data filter (PEP 706)."""
import tarfile

def restore(path, dest):
    with tarfile.open(path) as tar:
        tar.extractall(dest, filter="data")
