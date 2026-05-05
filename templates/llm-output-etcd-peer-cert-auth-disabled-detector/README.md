# llm-output-etcd-peer-cert-auth-disabled-detector

Detects etcd YAML configurations where the **peer** API (the
intra-cluster replication channel) is exposed on a non-loopback
interface without enforcing peer certificate authentication (mTLS
between cluster members).

## Why this matters

The etcd peer port (default `:2380`) carries Raft replication traffic
between members. If `peer-transport-security.peer-client-cert-auth`
is left at the default of `false`, any host that can reach `:2380`
can join or impersonate a cluster member, gaining the ability to
serve forged Raft state and effectively rewrite the keyspace — even
if the *client* port (`:2379`) is fully locked down with mTLS.

The hardened posture requires:

* `https://` on `listen-peer-urls` / `initial-advertise-peer-urls`,
* `peer-transport-security.cert-file` / `key-file` set, and
* `peer-transport-security.peer-client-cert-auth: true`.

LLM-generated multi-node etcd configs commonly harden the client
channel and forget the peer channel entirely, leaving cross-member
auth as plaintext or as TLS-without-mutual-auth. This is a different
mechanism from the client-cert-auth detector and lives in a
different YAML key (`peer-transport-security` vs
`client-transport-security`), so it is intentionally a separate
template.

## Rules

A finding is emitted when **all** of the following hold for an
`etcd*.yml` / `etcd*.yaml`:

1. The file parses as a YAML mapping that defines `listen-peer-urls`
   and/or `initial-advertise-peer-urls`.
2. At least one peer URL is non-loopback (host is not `127.0.0.1`,
   `::1`, `localhost`).
3. Either:
   - any peer URL uses `http://`, **or**
   - all peer URLs are `https://` but
     `peer-transport-security.cert-file` / `key-file` is unset, **or**
   - all peer URLs are `https://` but
     `peer-transport-security.peer-client-cert-auth` is not `true`.

A magic comment `# etcd-no-peer-cert-auth-allowed` anywhere in the
file suppresses the finding (use only for documented sandboxes /
single-node test clusters).

## Run

```
python3 detector.py examples/bad/01_plain_http_peer_all_interfaces.yml
./verify.sh
```

`verify.sh` exits 0 when the detector flags 4/4 bad and 0/4 good.

## Out of scope

* Client URLs (`listen-client-urls`) — handled by the existing
  `llm-output-etcd-client-cert-auth-disabled-detector`.
* etcd command-line flags / systemd unit files (no YAML in the
  picture). A separate detector should cover
  `etcd --listen-peer-urls`.
* Auto-TLS (`peer-auto-tls`): we do not treat self-signed auto-TLS
  as compliant, because it disables mutual identity verification.
