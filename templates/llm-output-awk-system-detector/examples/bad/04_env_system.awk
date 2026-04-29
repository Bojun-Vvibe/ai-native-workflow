#!/usr/bin/awk -f
# system() built from ENVIRON -- env vars are attacker-controllable.
BEGIN { system("ls " ENVIRON["TARGET_DIR"]) }
