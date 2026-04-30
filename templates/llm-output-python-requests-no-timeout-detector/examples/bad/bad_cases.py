"""Bad HTTP calls — every line below should trigger."""
import requests
import httpx
import urllib3


# 1. Module-level requests calls — no timeout.
r = requests.get("https://example.com")

# 2. POST without timeout.
r = requests.post("https://example.com", json={"a": 1})

# 3. PUT without timeout.
r = requests.put("https://example.com", data=b"x")

# 4. DELETE without timeout.
r = requests.delete("https://example.com")

# 5. requests.request without timeout.
r = requests.request("GET", "https://example.com")

# 6. httpx convenience call without timeout.
r = httpx.get("https://example.com")

# 7. httpx POST without timeout.
r = httpx.post("https://example.com", json={"a": 1})

# 8. urllib3 PoolManager request without timeout.
http = urllib3.PoolManager().request("GET", "https://example.com")

# 9. Bound session method without timeout.
session = requests.Session()
r = session.get("https://example.com")

# 10. Bound session POST without timeout.
r = session.post("https://example.com", data=b"y")

# 11. Bound httpx client without timeout.
client = httpx.Client()
r = client.get("https://example.com")
