#!/bin/sh
# Production launch script for the api worker.
exec uwsgi \
    --http-socket :8000 \
    --module api.wsgi:application \
    --master \
    --processes 8 \
    --stats 0.0.0.0:1717 \
    --stats-http
