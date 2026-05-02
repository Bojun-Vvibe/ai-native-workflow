FROM couchdb:3.3
# Credentials are injected at runtime via Docker secrets / k8s
# secret env. We deliberately do NOT set COUCHDB_PASSWORD here.
EXPOSE 5984
