# A Dockerfile fragment that bakes a slapd invocation with no
# `-o disallow=bind_anon` and no `-f` / `-F` pointer to an external
# config — so the running daemon falls back to compiled-in defaults
# that allow anonymous bind.

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y slapd ldap-utils && rm -rf /var/lib/apt/lists/*
EXPOSE 389
CMD ["slapd", "-d", "256", "-h", "ldap:///"]
