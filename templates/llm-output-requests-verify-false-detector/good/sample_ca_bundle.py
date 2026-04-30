import requests

# Pinning to an explicit CA bundle path is fine.
requests.post(
    "https://example.invalid/api",
    json={"k": "v"},
    verify="/etc/ssl/certs/ca-bundle.crt",
    timeout=10,
)
