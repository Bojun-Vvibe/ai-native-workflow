# llm-output-etcd-client-cert-auth-disabled-detector

Detects etcd YAML configurations where the client API is exposed on a
non-loopback interface without enforcing client certificate
authentication (mTLS).

## Why this matters

etcd holds the source of truth for Kubernetes and many other control
planes. The default etcd posture is *no* client authentication: any
TCP client that can reach `:2379` can read every Secret, every lease,
and write arbitrary keys. The hardened posture requires:

* `https://` on `listen-client-urls` / `advertise-client-urls`,
* `client-transport-security.cert-file` / `key-file` set, and
* `client-transport-security.client-cert-auth: true`.

LLM-generated quickstart configs commonly omit `client-cert-auth`
entirely, leaving it at the insecure default of `false`, or use plain
`http://` on `0.0.0.0`.

## Rules

A finding is emitted when **all** of the following hold for an
`etcd*.yml` / `etcd*.yaml`:

1. The file parses as a YAML mapping that defines `listen-client-urls`
   and/or `advertise-client-urls`.
2. At least one URL is non-loopback (host is not `127.0.0.1`, `::1`,
   `localhost`).
3. Either:
   - any URL uses `http://`, **or**
   - all URLs are `https://` but `client-transport-security.cert-file`
     / `key-file` is unset, **or**
   - all URLs are `https://` but `client-transport-security.client-cert-auth`
     is not `true`.

A magic comment `# etcd-no-client-cert-auth-allowed` anywhere in the
file suppresses the finding (use only for documented sandboxes).

## Run

```
python3 detector.py examples/bad/01_plain_http_all_interfaces.yml
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* etcd command-line flags (no YAML in the picture). A separate
  detector should cover systemd unit files / `etcd --listen-client-urls`.
* Peer URLs (`listen-peer-urls`) — handled by a separate peer-mTLS
  detector.
