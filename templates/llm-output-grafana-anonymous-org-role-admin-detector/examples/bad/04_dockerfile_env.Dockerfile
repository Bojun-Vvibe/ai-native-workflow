FROM grafana/grafana:10.4.0

# Public, "anyone can edit" dashboards. Disastrous in prod.
ENV GF_AUTH_ANONYMOUS_ENABLED=true
ENV GF_AUTH_ANONYMOUS_ORG_ROLE=Editor
ENV GF_AUTH_ANONYMOUS_ORG_NAME="Main Org."

EXPOSE 3000
