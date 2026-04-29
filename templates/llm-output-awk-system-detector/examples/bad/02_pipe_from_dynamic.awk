#!/usr/bin/awk -f
# Reads the URL out of a field and pipes it through curl.
{
  cmd = "curl -s " $2
  cmd | getline body
  print body
}
