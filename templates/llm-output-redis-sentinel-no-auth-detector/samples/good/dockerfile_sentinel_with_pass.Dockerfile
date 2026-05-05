FROM redis:7-alpine
EXPOSE 26379
COPY sentinel.conf /etc/redis/sentinel.conf
# Sentinel config file pins bind to a private interface, sets requirepass
# and per-master auth-pass. CMD does not override any of that.
CMD ["redis-sentinel", "/etc/redis/sentinel.conf", "--requirepass", "$(cat /run/secrets/sentinel_pass)"]
