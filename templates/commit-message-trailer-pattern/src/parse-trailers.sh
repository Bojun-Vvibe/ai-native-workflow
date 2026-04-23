#!/usr/bin/env bash
# Read git log over a range and emit a CSV of agent-cost trailers.
# Usage: parse-trailers.sh [<git-log-range>]
# Default range: last 30 days.
set -eu
range="${1:-}"
if [ -z "$range" ]; then
  range="--since=30.days"
fi

echo "sha,model,tokens_in,tokens_out,cache_hit_rate,mission_id"

git log $range --format=$'__SHA__%h\n%(trailers:only=true,unfold=true)__END__' |
awk '
  BEGIN { sha=""; model=""; ti=""; to=""; chr=""; mid=""; }
  /^__SHA__/ {
    if (sha != "") {
      printf "%s,%s,%s,%s,%s,%s\n", sha, model, ti, to, chr, mid;
    }
    sha = substr($0, 8);
    model=""; ti=""; to=""; chr=""; mid="";
    next;
  }
  /^__END__/ { next }
  /^Model: /          { model=substr($0,8); next }
  /^Tokens-In: /      { ti=substr($0,12);   next }
  /^Tokens-Out: /     { to=substr($0,13);   next }
  /^Cache-Hit-Rate: / { chr=substr($0,17);  next }
  /^Mission-Id: /     { mid=substr($0,13);  next }
  END {
    if (sha != "") {
      printf "%s,%s,%s,%s,%s,%s\n", sha, model, ti, to, chr, mid;
    }
  }
'
