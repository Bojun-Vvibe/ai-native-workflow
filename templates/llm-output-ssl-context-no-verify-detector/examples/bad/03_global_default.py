"""bad: poisons the global default HTTPS context for the whole process."""
import ssl
from urllib.request import urlopen

ssl._create_default_https_context = ssl._create_unverified_context
print(urlopen("https://example.invalid/").status)
