"""Good: only mentions extractall in a comment / docstring, no actual call.
Also: a tarfile.extractall belongs to the sibling tarfile detector and
should not be flagged here."""
import tarfile


def unpack_tar(arc: str, dest: str) -> None:
    """Note: this is *tarfile*, not zipfile.

    The phrase ZipFile().extractall() appears here only inside a
    docstring as a reference to the sibling detector.
    """
    with tarfile.open(arc) as tf:
        tf.extractall(dest)  # tarfile, handled elsewhere
