"""Good: explicit per-member realpath check before writing."""
import os
import zipfile


def _safe_extract(zf: zipfile.ZipFile, dest: str) -> None:
    dest_abs = os.path.realpath(dest)
    for member in zf.namelist():
        target = os.path.realpath(os.path.join(dest, member))
        if not target.startswith(dest_abs + os.sep) and target != dest_abs:
            raise RuntimeError(f"unsafe path in archive: {member}")
        zf.extract(member, dest)


def unpack(arc: str, dest: str) -> None:
    with zipfile.ZipFile(arc) as zf:
        _safe_extract(zf, dest)
