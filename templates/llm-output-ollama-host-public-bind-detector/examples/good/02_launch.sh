#!/usr/bin/env bash
# launcher binding only to loopback; remote access via SSH tunnel
set -e
export OLLAMA_HOST=127.0.0.1:11434
exec ollama serve
