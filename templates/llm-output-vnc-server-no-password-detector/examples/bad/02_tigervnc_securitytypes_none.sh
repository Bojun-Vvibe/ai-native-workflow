#!/usr/bin/env bash
# Headless desktop for CI screenshots.
Xvnc :1 -geometry 1920x1080 -depth 24 -SecurityTypes None &
