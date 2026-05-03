#!/usr/bin/env bash
# launch typesense without any api key flag — anyone reaching 8108 is admin
typesense-server --data-dir=/var/lib/typesense --listen-address=0.0.0.0
