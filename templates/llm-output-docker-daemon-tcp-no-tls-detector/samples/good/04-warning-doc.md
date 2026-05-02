# Doc snippet that warns AGAINST exposing the Docker daemon plaintext.
# Never run:
#   dockerd -H tcp://0.0.0.0:2375
# The Docker daemon API has no built-in auth; plaintext 2375 hands root
# on the host to anyone who can reach the port. Use 2376 with --tlsverify.
