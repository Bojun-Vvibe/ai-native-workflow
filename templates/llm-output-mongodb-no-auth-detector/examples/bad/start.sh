# Bad: explicit --noauth on the CLI and a bare mongod invocation.
#!/usr/bin/env bash
set -e

mongod --dbpath /data/db --bind_ip 0.0.0.0 --noauth &
mongod --dbpath /data/db2 --bind_ip 0.0.0.0 --port 27018 &

wait
