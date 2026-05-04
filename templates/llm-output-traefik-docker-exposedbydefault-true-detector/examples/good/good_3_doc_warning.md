# Traefik docker provider hardening

Do **not** leave the docker provider in its default expose-everything
mode. The recommended posture is:

```yaml
providers:
  docker:
    exposedByDefault: false
```

and then add `traefik.enable=true` per container that should be
routed. This is opt-in instead of opt-out.

If you absolutely must invert the default, use a `constraints` filter
so only labelled containers are exposed:

```yaml
providers:
  docker:
    exposedByDefault: false
    constraints: "Label(`routable`,`true`)"
```
