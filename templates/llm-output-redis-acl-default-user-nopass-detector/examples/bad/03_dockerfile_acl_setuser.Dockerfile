FROM redis:7
# Bootstrap an "admin" user without a password — same pitfall as legacy
# requirepass-less deployments, just dressed up in ACL syntax.
RUN echo 'port 6379' > /usr/local/etc/redis/redis.conf
CMD ["sh", "-c", "redis-server /usr/local/etc/redis/redis.conf & sleep 2 && redis-cli ACL SETUSER admin on nopass ~* +@all && wait"]
