#!/usr/bin/env bash
# Curl with no shell pipe; downstream is `tee`, not an interpreter.
curl -fsSL https://example.com/log.txt | tee /var/log/example.log
