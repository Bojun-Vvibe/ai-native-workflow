import requests

payload = {"k": "v"}
# verify defaults to True; explicit False here is the pattern we want flagged.
requests.post("https://example.invalid/api", json=payload, verify=False)
