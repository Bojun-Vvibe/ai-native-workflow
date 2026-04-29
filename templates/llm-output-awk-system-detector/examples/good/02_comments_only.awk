#!/usr/bin/awk -f
# Comment mentions system("rm -rf $1") and "cmd" | getline x as docs only.
# Actual code does no shell-out.
{
  # We could call system("rm " $1) here, but we will not.
  print $1, $2
}
