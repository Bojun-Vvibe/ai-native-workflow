#!/usr/bin/env bash
# detector.sh — flag NiFi configs that pin default/weak single-user
# credentials or expose the single-user provider on a public listener.
# Usage: detector.sh <file> [<file>...]
# Output: one FLAG line per finding. Always exits 0.

set -u

flag() {
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1 + 2: login-identity-providers.xml with SingleUserLoginIdentityProvider
  if grep -E 'SingleUserLoginIdentityProvider' "$f" >/dev/null 2>&1; then
    # Signal 1: Username = admin / empty
    awk '
      /<property[[:space:]]+name="Username"[[:space:]]*>/ {
        line=$0
        # extract between > and </
        match(line, /<property[[:space:]]+name="Username"[[:space:]]*>[^<]*<\/property>/)
        if (RSTART>0) {
          val=substr(line, RSTART, RLENGTH)
          sub(/.*">/, "", val); sub(/<\/property>.*/, "", val)
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
          lc=tolower(val)
          if (lc=="admin" || lc=="" ) {
            printf "%d:%s\n", NR, $0
          }
        }
      }
    ' "$f" 2>/dev/null \
      | while IFS=: read -r ln rest; do
          flag S1 "$f" "$ln" "$rest"
        done

    # Signal 2: Password literal (non-empty, not ${...})
    awk '
      /<property[[:space:]]+name="Password"[[:space:]]*>/ {
        line=$0
        match(line, /<property[[:space:]]+name="Password"[[:space:]]*>[^<]*<\/property>/)
        if (RSTART>0) {
          val=substr(line, RSTART, RLENGTH)
          sub(/.*">/, "", val); sub(/<\/property>.*/, "", val)
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
          if (val != "" && substr(val,1,2) != "${") {
            printf "%d:%s\n", NR, $0
          }
        }
      }
    ' "$f" 2>/dev/null \
      | while IFS=: read -r ln rest; do
          flag S2 "$f" "$ln" "$rest"
        done
  fi

  # Signal 3: nifi.properties with single-user-provider AND public https.host
  if grep -E '^nifi\.security\.user\.login\.identity\.provider[[:space:]]*=[[:space:]]*single-user-provider' "$f" >/dev/null 2>&1; then
    awk '
      /^nifi\.web\.https\.host[[:space:]]*=/ {
        v=$0
        sub(/^nifi\.web\.https\.host[[:space:]]*=[[:space:]]*/, "", v)
        gsub(/[[:space:]]+$/, "", v)
        if (v=="" || v=="0.0.0.0" || v=="[::]" ) {
          printf "%d:%s\n", NR, $0
        } else if (v !~ /^127\./ && v != "localhost" && v != "[::1]") {
          printf "%d:%s\n", NR, $0
        }
      }
    ' "$f" 2>/dev/null \
      | while IFS=: read -r ln rest; do
          flag S3 "$f" "$ln" "$rest"
        done
  fi

  # Signal 4: authorizers.xml with single-user-authorizer as active authorizer
  if grep -E '<authorizer>' "$f" >/dev/null 2>&1; then
    # find lines selecting single-user-authorizer that are NOT inside a comment
    awk '
      BEGIN { in_comment=0 }
      {
        line=$0
        # crude comment tracking
        tmp=line
        while (1) {
          if (in_comment) {
            p=index(tmp, "-->")
            if (p==0) { tmp=""; break }
            tmp=substr(tmp, p+3); in_comment=0
          } else {
            p=index(tmp, "<!--")
            if (p==0) break
            rest=substr(tmp, p+4)
            q=index(rest, "-->")
            if (q==0) {
              tmp=substr(tmp,1,p-1); in_comment=1; break
            } else {
              tmp=substr(tmp,1,p-1) substr(rest, q+3)
            }
          }
        }
        if (tmp ~ /<identifier>[[:space:]]*single-user-authorizer[[:space:]]*<\/identifier>/) {
          printf "%d:%s\n", NR, line
        }
      }
    ' "$f" 2>/dev/null \
      | while IFS=: read -r ln rest; do
          flag S4 "$f" "$ln" "$rest"
        done
  fi
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
