"""Bad: shutil.unpack_archive — format-agnostic, same risk."""
import shutil

def restore(path, dest):
    shutil.unpack_archive(path, dest)
