"""bad: explicit unverified context."""
import ssl
from urllib.request import urlopen

ctx = ssl._create_unverified_context()
resp = urlopen("https://example.invalid/", context=ctx)
print(resp.read())
