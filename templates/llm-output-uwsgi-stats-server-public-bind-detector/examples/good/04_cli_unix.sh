#!/bin/sh
# Production launch script with stats bound to a unix socket.
exec uwsgi \
    --http-socket :8000 \
    --module api.wsgi:application \
    --master \
    --processes 8 \
    --stats /run/uwsgi/stats.sock
