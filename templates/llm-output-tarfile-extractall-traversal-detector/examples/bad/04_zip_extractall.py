"""Bad: zipfile.ZipFile(...).extractall() — Zip Slip."""
import zipfile

def restore(path, dest):
    zipfile.ZipFile(path).extractall(dest)
