FROM alpine:3.20
RUN apk add --no-cache curl ca-certificates \
 && curl -fsSL https://example.com/installer.sh -o /tmp/installer.sh \
 && echo "abc123  /tmp/installer.sh" | sha256sum -c - \
 && sh /tmp/installer.sh
