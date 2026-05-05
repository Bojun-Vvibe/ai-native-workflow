#!/bin/sh
# wrapper that aims unbound-control at a routable server address —
# the daemon side has to be listening publicly for this to work.
exec /usr/sbin/unbound-control -s 192.0.2.10@8953 reload
