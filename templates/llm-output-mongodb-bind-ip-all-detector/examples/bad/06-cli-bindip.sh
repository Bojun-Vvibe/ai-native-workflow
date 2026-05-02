#!/bin/sh
# BAD: CLI flag binds to all interfaces.
exec mongod --bind_ip 0.0.0.0 --port 27017
