# llm-output-stunnel-server-verify-zero-detector

Detects `stunnel.conf` services running in **server mode**
(`client = no`, the default) that:

1. Forward to a **sensitive backend** (Redis, Postgres, MySQL,
   Mongo, etcd, Elasticsearch, Consul, RabbitMQ, MinIO, etc.), and
2. Accept **any TLS client** because either:
   - `verify = 0` is set explicitly, or
   - no `verify` / `verifyChain` / `verifyPeer` is set **and** no
     `CAfile` / `CApath` is configured to anchor trust, or
   - `verifyChain = no` / `verifyPeer = no` is set explicitly.

## Why this matters

Operators reach for stunnel when they want to bolt mTLS onto a
backend that does not natively speak TLS. The intended deployment
shape is:

    [redis-mtls]
    accept = 0.0.0.0:6390
    connect = 127.0.0.1:6379
    verify = 2
    CAfile = /etc/stunnel/clients-ca.pem

But almost every quickstart on the internet drops `verify = 0` "to
get it working", which silently turns the wrapper into a
TLS-terminating proxy that any TCP client on the network can use to
reach the now-public backend. The Redis / Mongo / etcd port that the
operator believed was "behind mTLS" is in practice exposed to the
entire L3 segment.

This detector flags that exact shape.

## What it detects

For each scanned `stunnel.conf`, the detector reports a finding when
a service section satisfies all of:

1. `client` is unset or `no` (server mode).
2. `connect` points at a port in the sensitive-backends list (full
   list in `detector.py`).
3. The service does **not** have any of:
   - `verify >= 1`
   - `verifyChain = yes` (or `verifyPeer = yes`)
   - `verify` unset **and** a `CAfile` / `CApath` configured.

## CWE references

- CWE-295: Improper Certificate Validation
- CWE-306: Missing Authentication for Critical Function
- CWE-441: Unintended Proxy or Intermediary ('Confused Deputy')

## False-positive surface

- `client = yes` services are out of scope (they are TLS clients,
  not servers).
- A service whose `connect` does not target a known sensitive port
  is not flagged. The aim is to surface the dangerous shape, not to
  scold every TLS terminator.
- A file that intentionally documents the vulnerable pattern can be
  suppressed with a comment containing `stunnel-verify-allowed`.

## Usage

    python3 detector.py path/to/stunnel.conf

Exit code: number of files with at least one finding (capped at 255).
Stdout format: `<file>:<line>:<reason>`.

Run `bash verify.sh` to execute the bundled good/bad fixtures.
