FROM grafana/grafana:10.4.0

# Production: anonymous off, real admin password from secret.
ENV GF_AUTH_ANONYMOUS_ENABLED=false
ENV GF_SECURITY_ADMIN_USER=admin
# secret mounted at runtime via /run/secrets/grafana_admin_pw
ENV GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_admin_pw

EXPOSE 3000
