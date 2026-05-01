FROM debian:stable-slim
ADD \
  https://example.com/big-payload.zip \
  /opt/payload.zip
