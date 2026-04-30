"""Bad: tar handle .extractall() with no filter= kwarg."""
import tarfile

def restore(path, dest):
    tar = tarfile.open(path)
    tar.extractall(dest)
    tar.close()
