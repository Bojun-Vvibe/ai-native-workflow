# bad: scripts that need fail-fast preamble but don't have one.

A classic "install everything" snippet with a shebang but no `set -e`.
The `apt-get install` step can fail and the script will still run
`make install`:

```bash
#!/usr/bin/env bash
apt-get update
apt-get install -y libfoo-dev
./configure --prefix=/opt/app
make
make install
```

A multi-step deploy block with a function definition and a pipeline,
no shebang, no `set -e`. Hidden failures here will silently let the
script "succeed":

```sh
deploy() {
  tar czf /tmp/release.tgz dist/
  scp /tmp/release.tgz user@host:/srv/
  ssh user@host 'cd /srv && tar xzf release.tgz'
}

deploy
curl -fsSL https://example.test/healthz | grep -q ok
echo "deploy complete"
```

A loop-and-pipeline-heavy block — same problem, different shape:

```bash
for env in staging prod; do
  echo "running migrations against ${env}"
  psql "$env" -c 'select 1' | head -1
done
echo "done"
```

A `pipefail`-only preamble is *not* enough — pipefail without errexit
still continues past failures. This block must be flagged:

```bash
#!/usr/bin/env bash
set -o pipefail
curl https://example.test/cfg | jq .key > /etc/app.cfg
systemctl restart app
```
