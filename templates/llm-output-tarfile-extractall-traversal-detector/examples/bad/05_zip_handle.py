"""Bad: zip handle .extractall on conventional name."""
import zipfile

def restore(path, dest):
    zf = zipfile.ZipFile(path)
    zf.extractall(dest)
