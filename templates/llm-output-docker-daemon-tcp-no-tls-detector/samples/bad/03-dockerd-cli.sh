# dockerd launched directly on a remote host — no TLS, no client auth.
dockerd --host=tcp://0.0.0.0:2375 --host=unix:///var/run/docker.sock
