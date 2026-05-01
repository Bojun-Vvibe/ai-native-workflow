FROM debian:stable-slim
# BuildKit ADD with --checksum= verifies integrity, so we accept it.
ADD --checksum=sha256:deadbeefcafebabe1234567890abcdef1234567890abcdef1234567890abcdef \
    https://example.com/payload.tar.gz /opt/payload.tar.gz
