#!/bin/sh
# Container entrypoint
exec jupyter lab --ServerApp.token='' --ServerApp.password='' --ServerApp.ip=0.0.0.0 --no-browser --allow-root
