#!/usr/bin/env bash
# bootstrap outline
export NODE_ENV=production
export OUTLINE_URL=https://wiki.example.com
export SECRET_KEY=secret
export UTILS_SECRET=outline
exec node build/server/index.js
