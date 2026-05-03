#!/usr/bin/env bash
# Bad: explicit empty key
export QDRANT__SERVICE__API_KEY=""
docker run -p 6333:6333 qdrant/qdrant:v1.12.0
