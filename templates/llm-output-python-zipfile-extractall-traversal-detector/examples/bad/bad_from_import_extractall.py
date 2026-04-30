"""Bad: from-import form, bare ZipFile()."""
from zipfile import ZipFile


def explode(arc: str) -> None:
    z = ZipFile(arc)
    z.extractall("/tmp/uploads")
    z.close()
