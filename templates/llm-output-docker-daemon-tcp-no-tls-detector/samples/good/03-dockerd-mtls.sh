# dockerd with mutual TLS on 2376 — the documented secure remote API setup.
dockerd \
  --tlsverify \
  --tlscacert=/etc/docker/ca.pem \
  --tlscert=/etc/docker/server-cert.pem \
  --tlskey=/etc/docker/server-key.pem \
  -H=tcp://0.0.0.0:2376 \
  -H unix:///var/run/docker.sock
