#!/usr/bin/awk -f
# Pipe-from a *literal* command (no interpolation). Considered safe by
# this detector; the command string is fixed at author time.
BEGIN {
  "date -u +%Y-%m-%d" | getline today
  print today
}
