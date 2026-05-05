FROM crowdsecurity/crowdsec:latest
EXPOSE 8080
# Operator wanted remote bouncers without setting up TLS. The LAPI is
# now reachable from any network the host can see.
CMD ["crowdsec", "-c", "/etc/crowdsec/config.yaml", "--listen-uri", "0.0.0.0:8080"]
