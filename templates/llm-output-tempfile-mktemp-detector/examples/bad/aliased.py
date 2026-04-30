from tempfile import mktemp as mk


def upload_path() -> str:
    return mk(suffix=".upload")
