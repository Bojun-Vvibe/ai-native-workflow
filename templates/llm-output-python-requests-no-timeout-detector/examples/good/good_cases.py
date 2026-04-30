"""Safe HTTP calls — none of these should trigger."""
import requests
import httpx


# Explicit timeout.
r = requests.get("https://example.com", timeout=5)

# Tuple timeout (connect, read).
r = requests.post("https://example.com", json={"a": 1}, timeout=(3, 10))

# Explicit timeout=None — caller deliberately opted into infinite
# wait. We don't second-guess that; suppression marker would also
# work. The detector's rule is "any timeout= kwarg passes".
r = requests.put("https://example.com", data=b"x", timeout=None)

# Bound session with timeout.
session = requests.Session()
r = session.get("https://example.com", timeout=5)
r = session.post("https://example.com", data=b"y", timeout=10)

# httpx with timeout.
r = httpx.get("https://example.com", timeout=5.0)

# httpx Client with timeout configured at construction time —
# subsequent get() calls inherit it; we still want a visible
# timeout= at the call site for the linter, but a per-client
# default is equally fine. Use the suppression marker.
client = httpx.Client(timeout=5.0)
r = client.get("https://example.com")  # no-timeout-ok

# Discussion in a string literal should not trigger:
note = "Never call requests.get(url) without timeout=."

# Discussion in a comment should not trigger:
# requests.post("https://example.com") would be unsafe.
