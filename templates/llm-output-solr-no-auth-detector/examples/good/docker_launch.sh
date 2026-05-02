# Container launch with security.json mounted from a vault-rendered file
docker run -d --name solr \
  -p 127.0.0.1:8983:8983 \
  -v /etc/solr/security.json:/var/solr/data/security.json:ro \
  solr:9.5
