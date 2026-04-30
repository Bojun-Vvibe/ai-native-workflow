"""Good: docstring mention of extractall, no actual call."""

def how_to_extract():
    """Use tar.extractall(dest, filter='data') for safety.

    Avoid bare tarfile.open(p).extractall(d) because it permits
    Zip Slip via .. members.
    """
    return None
