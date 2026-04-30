"""Bad: webhook handler that unzips a fetched bundle in-place."""
import zipfile
import io
import urllib.request


def fetch_and_install(url: str, install_dir: str) -> None:
    data = urllib.request.urlopen(url).read()
    bundle = zipfile.ZipFile(io.BytesIO(data))
    bundle.extractall(install_dir)
