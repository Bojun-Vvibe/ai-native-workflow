"""Bad: shutil.unpack_archive — same flaw, stdlib wrapper."""
import shutil


def unpack_user_archive(path: str, dest: str) -> None:
    shutil.unpack_archive(path, dest)
