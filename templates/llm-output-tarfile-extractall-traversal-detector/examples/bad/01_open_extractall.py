"""Bad: bare tarfile.open(...).extractall() — no filter."""
import tarfile

def restore(path, dest):
    tarfile.open(path).extractall(dest)
