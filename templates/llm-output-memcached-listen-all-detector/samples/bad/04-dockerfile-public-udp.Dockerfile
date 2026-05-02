# Dockerfile — bakes a public-bound, UDP-enabled memcached into the image.
FROM alpine:3.19
RUN apk add --no-cache memcached
EXPOSE 11211/tcp 11211/udp
USER memcached
CMD ["memcached", "-l", "0.0.0.0", "-p", "11211", "-U", "11211", "-m", "256"]
