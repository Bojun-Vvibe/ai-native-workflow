# llm-output-clickhouse-default-no-password-detector

Detect ClickHouse `users.xml` snippets where the built-in `default` user has an
**empty password** (or no `<password*>` tag at all). LLMs frequently emit this
shape when asked to "set up ClickHouse" because it mirrors the upstream
out-of-the-box example. Combined with the equally common `<ip>::/0</ip>`
network ACL, it produces an unauthenticated, internet-reachable database.

## What bad LLM output looks like

```xml
<clickhouse>
  <users>
    <default>
      <password></password>          <!-- empty -->
      <networks><ip>::/0</ip></networks>
    </default>
  </users>
</clickhouse>
```

Variants the detector also catches:
- `<password_sha256_hex></password_sha256_hex>` (empty hash)
- `<password_double_sha1_hex></password_double_sha1_hex>` (empty hash)
- A `<default>` block that contains **no** `<password*>` tag at all

## What good LLM output looks like

A non-empty plain `<password>` element, or a non-empty
`<password_sha256_hex>` / `<password_double_sha1_hex>` populated with a real
hex digest. Pair with a restrictive `<networks>` ACL.

## Run the smoke test

```sh
bash detect.sh samples/bad/* samples/good/*
```

Expected output:

```
BAD  samples/bad/empty_password.xml
BAD  samples/bad/empty_sha256.xml
BAD  samples/bad/no_password_tag.xml
GOOD samples/good/double_sha1_set.xml
GOOD samples/good/plain_password_set.xml
GOOD samples/good/sha256_set.xml
bad=3/3 good=0/3 PASS
```

Exit status is `0` only when every bad sample is flagged and zero good samples
are flagged.

## How to wire into a pipeline

Pipe LLM-emitted XML through `detect.sh /dev/stdin` or save to a temp file in a
`samples/bad/`-shaped path and invoke the script. Non-zero exit means the
generated config still has the insecure-default `default` user.
