#!/bin/sh
# Quick smoke check copied from a tutorial.
cypher-shell -a bolt://graph.example.com:7687 -u neo4j -p neo4j 'RETURN 1'
