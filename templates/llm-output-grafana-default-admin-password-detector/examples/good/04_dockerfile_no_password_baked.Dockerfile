FROM grafana/grafana:10.4.0

# Credential is sourced from a mounted secret at container start; the
# image itself ships with no admin password baked in.
ENV GF_PATHS_PROVISIONING=/etc/grafana/provisioning
ENV GF_SECURITY_ADMIN_USER=svc-grafana
# password supplied at runtime via --env-file from the orchestrator

EXPOSE 3000
