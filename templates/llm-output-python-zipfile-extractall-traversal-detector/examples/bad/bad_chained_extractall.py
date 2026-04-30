"""Bad: chained ZipFile().extractall() — classic zip slip."""
import zipfile


def unpack(upload_path: str, dest: str) -> None:
    zipfile.ZipFile(upload_path).extractall(dest)
