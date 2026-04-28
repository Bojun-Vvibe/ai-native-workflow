# good: equivalent scripts that DO carry a fail-fast preamble.

The "install everything" snippet, but now with `set -euo pipefail`
right after the shebang:

```bash
#!/usr/bin/env bash
set -euo pipefail
apt-get update
apt-get install -y libfoo-dev
./configure --prefix=/opt/app
make
make install
```

Multi-step deploy block with `set -e` (long form):

```sh
set -o errexit
deploy() {
  tar czf /tmp/release.tgz dist/
  scp /tmp/release.tgz user@host:/srv/
  ssh user@host 'cd /srv && tar xzf release.tgz'
}

deploy
curl -fsSL https://example.test/healthz | grep -q ok
echo "deploy complete"
```

Loop-and-pipeline block with the canonical `set -eu`:

```bash
set -eu
for env in staging prod; do
  echo "running migrations against ${env}"
  psql "$env" -c 'select 1' | head -1
done
echo "done"
```

A short one-liner snippet — no shebang, no control flow — is below
our threshold and should NOT be flagged even without `set -e`:

```bash
echo "hello, world"
```

A two-line snippet with no control flow and no pipeline is also
under the threshold:

```sh
ls -la
pwd
```
