#!/usr/bin/env bash
# detect.sh — flag tftpd-hpa / in.tftpd defaults files (and equivalent
# systemd unit ExecStart lines) that put the daemon into write-enabled
# mode. The TFTP protocol has no authentication, no integrity, no
# transport encryption: a tftpd that accepts writes lets any host that
# can reach UDP/69 overwrite arbitrary files inside the TFTP root
# (commonly PXE images, switch firmware, router configs). The two
# write-enabling switches we flag are:
#   -c           short form of --create (allow creating new files)
#   --create     long form
# Some operators also pass --umask 0000 with -c to make the writes
# group/world-writable; we do NOT flag --umask alone because it is only
# dangerous together with writes being enabled. We DO flag the upstream
# secure-mode bypass `--no-blocksize2` only when combined with --create
# (write-amplification trick) — see bad-4.
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS (every bad flagged, no good flagged).
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it looks like tftpd-hpa / in.tftpd configuration AND
# contains a write-enabling option (-c or --create) on a non-comment
# line, scoped to the OPTIONS / ExecStart string.
is_bad() {
  local f="$1"
  awk '
    BEGIN {
      saw_tftpd = 0
      bad       = 0
    }
    {
      raw = $0
      lc  = tolower(raw)

      # Heuristic: must look like tftpd / in.tftpd / tftpd-hpa usage.
      if (lc ~ /tftpd-hpa/)               saw_tftpd = 1
      if (lc ~ /in\.tftpd/)               saw_tftpd = 1
      if (lc ~ /\/usr\/sbin\/in\.tftpd/)  saw_tftpd = 1
      if (lc ~ /tftp_options|tftp_directory|tftp_username/) saw_tftpd = 1
      # systemd unit for tftpd-hpa typically has Description=tftp-hpa or
      # ExecStart=/usr/sbin/in.tftpd.
      if (lc ~ /description=.*tftp/)      saw_tftpd = 1

      # Strip leading whitespace before deciding what is a comment.
      stripped = raw
      sub(/^[[:space:]]+/, "", stripped)
      # Skip comment-only lines (#, ;).
      if (stripped ~ /^(#|;)/) next
      # Strip trailing # comment so "OPTIONS=... # writes" prose does not match.
      no_comment = raw
      sub(/[ \t]#.*$/, "", no_comment)

      # Look for -c / --create only inside an OPTIONS=... assignment or
      # an ExecStart= line, so that a -c that means something else in an
      # unrelated tool (e.g. `ssh -c aes256`) does not flag.
      payload = ""
      if (no_comment ~ /(^|[[:space:]])(TFTP_OPTIONS|OPTIONS|ARGS|DAEMON_OPTS)[[:space:]]*=/) {
        payload = no_comment
      } else if (no_comment ~ /ExecStart[[:space:]]*=.*(in\.tftpd|tftpd-hpa)/) {
        payload = no_comment
      } else if (no_comment ~ /in\.tftpd([[:space:]]|$)/) {
        # Bare invocation in a shell script (matches /usr/sbin/in.tftpd too).
        payload = no_comment
      }

      if (payload != "") {
        # Normalise: replace quotes with spaces so token boundaries are uniform.
        norm = payload
        gsub(/["\x27]/, " ", norm)
        # --create as a whole token.
        if (norm ~ /(^|[[:space:]=])--create([[:space:]=]|$)/) bad = 1
        # Single-dash short option that contains c (e.g. -c, -cv, -vc, -vcs).
        # Must start with a single - (not --), then [a-zA-Z]+ that includes a c,
        # bounded by whitespace.
        n = split(norm, toks, /[[:space:]]+/)
        for (i = 1; i <= n; i++) {
          t = toks[i]
          if (t ~ /^-[a-zA-Z]+$/ && t !~ /^--/) {
            # short option group; flag if it contains a literal c
            if (index(t, "c") > 0) bad = 1
          }
        }
      }
    }
    END {
      if (!saw_tftpd) exit 1
      if (bad)        exit 0
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
