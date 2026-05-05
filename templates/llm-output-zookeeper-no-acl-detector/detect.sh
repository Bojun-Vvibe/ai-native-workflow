#!/usr/bin/env bash
# detect.sh — flag ZooKeeper client snippets / setup scripts that create
# znodes with a wide-open ACL: `Ids.OPEN_ACL_UNSAFE` (Java/Kotlin/Scala),
# `OPEN_ACL_UNSAFE` (Python kazoo), or a literal `world:anyone:cdrwa`
# (zkCli.sh / setAcl shell). These ACLs grant CREATE+READ+WRITE+DELETE+ADMIN
# to every connected client — including anonymous ones — which means any
# attacker who reaches the ZooKeeper port can read secrets, alter cluster
# membership, or wipe znodes. ZooKeeper authentication (SASL/Kerberos) is
# orthogonal: a server that "requires SASL" still honours OPEN_ACL_UNSAFE
# znodes for unauthenticated clients. LLMs commonly emit this when asked to
# "create a config znode" because it is the path of least resistance and
# the official quickstart still shows it.
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS (every bad flagged, no good flagged).
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it looks like ZooKeeper client code / zkCli usage AND
# contains an open-ACL marker on a non-comment line.
is_bad() {
  local f="$1"
  awk '
    BEGIN {
      saw_zk = 0
      bad    = 0
    }
    {
      raw = $0
      lc  = tolower(raw)

      # Strip leading whitespace before deciding what is a comment.
      stripped = raw
      sub(/^[[:space:]]+/, "", stripped)

      # Heuristic: must look like ZooKeeper usage somewhere in the file.
      if (lc ~ /zookeeper/) saw_zk = 1
      if (lc ~ /kazooclient|zk\.create|zkclient|curatorframework|zkcli/) saw_zk = 1
      if (lc ~ /org\.apache\.zookeeper/) saw_zk = 1

      # Skip comment-only lines (//, #, ;, /* … */).
      if (stripped ~ /^(\/\/|#|;|\/\*|\*)/) next
      # Strip trailing line comment from java/scala/kotlin to avoid matching
      # OPEN_ACL_UNSAFE that is mentioned in a sentence.
      no_comment = raw
      sub(/\/\/.*$/, "", no_comment)
      sub(/#.*$/,    "", no_comment)
      lcnc = tolower(no_comment)

      # Java / Scala / Kotlin: Ids.OPEN_ACL_UNSAFE or ZooDefs.Ids.OPEN_ACL_UNSAFE
      if (no_comment ~ /(^|[^A-Za-z0-9_])OPEN_ACL_UNSAFE([^A-Za-z0-9_]|$)/) bad = 1

      # zkCli shell: setAcl /path world:anyone:cdrwa (any subset of cdrwa)
      if (lcnc ~ /world:anyone:[cdrwa]+/) bad = 1

      # ANYONE_ID_UNSAFE used as the only Id in an ACL list also opens it.
      if (no_comment ~ /(^|[^A-Za-z0-9_])ANYONE_ID_UNSAFE([^A-Za-z0-9_]|$)/ && lcnc ~ /perms\.all|0x1f|(^|[^0-9])31([^0-9]|$)/) bad = 1
    }
    END {
      if (!saw_zk) exit 1
      if (bad)     exit 0
      exit 1
    }
  ' "$f"
}

scan_one() {
  local f="$1"
  case "$f" in
    *samples/bad-*)  bad_total=$((bad_total+1))  ;;
    *samples/good-*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad-*)  bad_hits=$((bad_hits+1))  ;;
      *samples/good-*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f"
  fi
}

if [ "$#" -eq 0 ]; then
  tmp="$(mktemp)"
  cat > "$tmp"
  scan_one "$tmp"
  rm -f "$tmp"
else
  for f in "$@"; do scan_one "$f"; done
fi

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$bad_total" -gt 0 ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
