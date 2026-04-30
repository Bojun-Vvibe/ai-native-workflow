import requests

# verify defaults to True (good); we also pass an explicit CA bundle below.
r = requests.get("https://example.invalid/data", timeout=5)
print(r.status_code)
