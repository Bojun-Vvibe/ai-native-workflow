from tempfile import mktemp


def staging_path() -> str:
    return mktemp(suffix=".csv")


def render_to_temp() -> str:
    p = mktemp()
    return p
