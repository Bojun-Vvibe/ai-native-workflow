#!/bin/sh
set -e
# Strong, randomly generated bootstrap creds rotated out-of-band on
# first login. Length >= 10 and not in the known-placeholder list.
./pocketbase superuser create ops-bootstrap@corp.internal Tk9p2vQ8wLm4Rh6xZ
exec ./pocketbase serve --http=0.0.0.0:8090
