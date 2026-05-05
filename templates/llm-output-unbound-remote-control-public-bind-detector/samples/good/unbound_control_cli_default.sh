#!/bin/sh
# default invocation — talks to the local daemon over the unix-style
# loopback control channel; no -s flag needed.
exec /usr/sbin/unbound-control reload
