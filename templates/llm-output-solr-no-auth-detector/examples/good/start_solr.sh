#!/usr/bin/env bash
# Dev launcher, bound to loopback
bin/solr start -p 8983 -Dhost=127.0.0.1 -s /var/solr/data
