"""Good: tarfile with explicit tarfile.data_filter callable."""
import tarfile

def restore(path, dest):
    with tarfile.open(path) as tar:
        tar.extractall(dest, filter=tarfile.data_filter)
