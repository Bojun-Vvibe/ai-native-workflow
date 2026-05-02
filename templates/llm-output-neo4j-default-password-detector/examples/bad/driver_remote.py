from neo4j import GraphDatabase

# Connect to a remote Neo4j server using the install-default credentials.
driver = GraphDatabase.driver("bolt://graph.example.com:7687", auth=("neo4j", "neo4j"))
with driver.session() as session:
    session.run("MATCH (n) RETURN count(n)")
