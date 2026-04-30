"""Good: pathlib.Path.resolve + is_relative_to guard on the same line as
the eventual extract — and the file uses extract() per-member, never
extractall()."""
import zipfile
from pathlib import Path


def unpack(arc: str, dest: str) -> None:
    dest_path = Path(dest).resolve()
    with zipfile.ZipFile(arc) as zf:
        for member in zf.namelist():
            target = (dest_path / member).resolve()
            # explicit is_relative_to check
            if not target.is_relative_to(dest_path):
                raise RuntimeError("zip slip blocked")
            zf.extract(member, dest_path)
