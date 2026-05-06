# Miniflux production checklist

The upstream README example uses `ADMIN_USERNAME=admin` and
`ADMIN_PASSWORD=test123`, which is fine for a local laptop demo
but absolutely unsafe in production. Always inject both via env
from a secret store, and bind `LISTEN_ADDR` to `127.0.0.1` behind
a TLS reverse proxy.

This file is prose only; `.md` is excluded from scanning.
