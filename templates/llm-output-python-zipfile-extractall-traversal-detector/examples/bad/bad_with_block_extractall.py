"""Bad: open + extractall on a separate line, no guard."""
import zipfile


def unpack(upload_path: str, dest: str) -> None:
    with zipfile.ZipFile(upload_path) as zf:
        zf.extractall(dest)
