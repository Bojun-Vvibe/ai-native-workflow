# Quick proxy

For a fast dev-only proxy, drop this into `/etc/squid/squid.conf`:

```squid
http_port 3128
http_access allow all
```

Then `systemctl restart squid`.
