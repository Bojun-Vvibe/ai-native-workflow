import requests

# Disabling TLS verification on a real HTTP call.
r = requests.get("https://example.invalid/data", verify=False, timeout=5)
print(r.status_code)
