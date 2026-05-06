#!/bin/sh
set -e
# Bootstrap an admin if none exists, then start the server.
./pocketbase superuser upsert admin@example.com 1234567890
exec ./pocketbase serve --http=0.0.0.0:8090
