#!/usr/bin/awk -f
# Pure data transformation, no shell-out at all.
BEGIN { FS = "," }
{
  total += $2
}
END { print "sum:", total }
