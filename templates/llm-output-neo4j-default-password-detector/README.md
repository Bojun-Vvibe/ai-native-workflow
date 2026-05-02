# llm-output-neo4j-default-password-detector

Detects LLM-generated configuration or client snippets that ship a Neo4j
deployment with the install-default `neo4j` / `neo4j` credential pair, or
that disable Neo4j authentication entirely.

## What is flagged

* `dbms.security.auth_enabled=false` in `neo4j.conf`
* `NEO4J_AUTH=none` in shell / docker-compose / k8s env
* `NEO4J_AUTH=neo4j/neo4j` (the install default that the server *forces*
  the operator to rotate on first login — pinning it back to `neo4j` in
  config skips the rotation)
* Driver code that calls `GraphDatabase.driver(uri, auth=("neo4j", "neo4j"))`
  against a non-loopback URI
* `cypher-shell -u neo4j -p neo4j` against a non-loopback host

The default Neo4j account has full DBA privileges, so leaving any of
these on a network-reachable host is equivalent to publishing the
database.

## Suppression

Add the marker `neo4j-default-password-allowed` anywhere in the file
(typically in a comment in a lab fixture) to silence the detector.

## Run

```
./verify.sh
```

Expected:

```
bad=5/5 good=0/3
PASS
```
