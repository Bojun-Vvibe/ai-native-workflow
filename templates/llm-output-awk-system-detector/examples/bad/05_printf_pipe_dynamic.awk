#!/usr/bin/awk -f
# printf into a dynamic command -- same shape as `print | cmd`.
{
  outfile = $1
  printf("%s\n", $0) | ("gzip -c > " outfile ".gz")
}
