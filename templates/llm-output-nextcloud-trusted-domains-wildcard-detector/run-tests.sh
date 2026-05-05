#!/usr/bin/env bash
# run-tests.sh — worked example runner for llm-output-nextcloud-trusted-domains-wildcard-detector
set -u
cd "$(dirname "$0")"
bash detect.sh samples/bad-*.txt samples/good-*.txt
