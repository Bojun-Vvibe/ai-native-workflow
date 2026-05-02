import os
from neo4j import GraphDatabase

# Production: credentials come from a secret manager, not the install default.
uri = os.environ["NEO4J_URI"]
user = os.environ["NEO4J_USER"]
password = os.environ["NEO4J_PASSWORD"]

driver = GraphDatabase.driver(uri, auth=(user, password))
with driver.session() as session:
    session.run("MATCH (n) RETURN count(n)")
