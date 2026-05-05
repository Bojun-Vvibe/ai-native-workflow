# Dockerfile that points slapd at an external `-F` config directory we
# cannot inspect from this file alone. The detector defers to the file-
# based rules and does not flag the invocation by itself.

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y slapd ldap-utils && rm -rf /var/lib/apt/lists/*
EXPOSE 389
CMD ["slapd", "-d", "256", "-h", "ldap:///", "-F", "/etc/openldap/slapd.d"]
