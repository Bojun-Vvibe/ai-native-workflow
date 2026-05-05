FROM crowdsecurity/crowdsec:latest
EXPOSE 8080
# Wildcard bind is intentional: this image only ever runs inside an
# overlay network that enforces mTLS at the mesh layer, and the
# bouncer enrollment endpoint is gated by an external authz policy.
# crowdsec-lapi-listen-public-allowed
CMD ["crowdsec", "-c", "/etc/crowdsec/config.yaml", "--listen-uri", "0.0.0.0:8080"]
