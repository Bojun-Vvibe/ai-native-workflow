#!/usr/bin/env bash
# detect.sh — flag Ansible configuration that disables SSH host-key
# checking. When `host_key_checking = False` (in `ansible.cfg` under
# `[defaults]`) or `ANSIBLE_HOST_KEY_CHECKING=False` (in env files /
# CI variables / shell scripts) is in effect, Ansible will silently
# accept any host key on first connect AND silently accept a *changed*
# host key on subsequent connects. That makes every managed host
# trivially impersonable by anyone in path: a man-in-the-middle (a
# rogue DHCP server, an ARP-spoofing attacker on the LAN, a hijacked
# jump box) can present its own SSH host key and Ansible will hand
# over `become` credentials — including sudo passwords passed via
# `--ask-become-pass`, secrets from Vault that get templated into
# files, and the entire content of any `copy:` task.
#
# We deliberately distinguish three carriers because LLMs emit all of
# them when asked to "make ansible just work in CI":
#   1. INI:   [defaults] block in ansible.cfg with host_key_checking = False
#   2. ENV:   ANSIBLE_HOST_KEY_CHECKING=False (or =0, =no, =off) in
#             a shell script, .env-like file, Dockerfile, or systemd unit
#   3. YAML:  inventory group_vars / host_vars where ansible_ssh_extra_args
#             contains -o StrictHostKeyChecking=no or -o
#             UserKnownHostsFile=/dev/null
# All three are equally dangerous; the detector flags any of them as
# long as the file otherwise looks Ansible-related.
#
# Per-file BAD/GOOD lines plus a tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only on PASS (every bad flagged, no good flagged).
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it looks Ansible-related AND contains a host-key-check
# disabling marker on a non-comment line, in the right scope.
is_bad() {
  local f="$1"
  awk '
    BEGIN {
      saw_ansible = 0
      in_defaults = 0
      bad         = 0
    }
    {
      raw = $0
      lc  = tolower(raw)

      # Heuristic: must look like Ansible somewhere in the file.
      if (lc ~ /ansible/) saw_ansible = 1
      if (lc ~ /\[defaults\]/) saw_ansible = 1
      if (lc ~ /ansible_ssh_/ || lc ~ /ansible_user|ansible_become/) saw_ansible = 1
      if (lc ~ /inventory|playbook|hosts\.ini|group_vars|host_vars/) saw_ansible = 1

      # Track INI section so we only flag host_key_checking inside
      # [defaults] (it is the only section where ansible reads it).
      stripped = raw
      sub(/^[[:space:]]+/, "", stripped)
      sub(/[[:space:]]+$/, "", stripped)
      if (stripped ~ /^\[[^]]+\]$/) {
        if (tolower(stripped) == "[defaults]") in_defaults = 1
        else                                   in_defaults = 0
        next
      }

      # Skip comment-only lines.
      if (stripped ~ /^(#|;)/) next
      # Strip trailing # or ; comment.
      no_comment = raw
      sub(/[ \t]#.*$/,  "", no_comment)
      sub(/[ \t];.*$/,  "", no_comment)
      lcnc = tolower(no_comment)

      # 1. INI form: host_key_checking = false  (only in [defaults])
      if (in_defaults && lcnc ~ /^[[:space:]]*host_key_checking[[:space:]]*=[[:space:]]*(false|0|no|off)[[:space:]]*$/) {
        bad = 1
      }

      # 2. ENV form: ANSIBLE_HOST_KEY_CHECKING=False (or =0/no/off),
      #    optionally preceded by `export ` or `environment:` mapping
      #    style "  ANSIBLE_HOST_KEY_CHECKING: False".
      if (lcnc ~ /(^|[[:space:]"\x27])ansible_host_key_checking[[:space:]]*[=:][[:space:]]*[\x27"]?(false|0|no|off)[\x27"]?([[:space:]]|$)/) {
        bad = 1
      }

      # 3. YAML inventory var: ansible_ssh_extra_args containing
      #    StrictHostKeyChecking=no  OR  UserKnownHostsFile=/dev/null
      if (lcnc ~ /ansible_ssh_(common|extra)_args/ || lcnc ~ /ansible_ssh_args/) {
        if (lcnc ~ /stricthostkeychecking[[:space:]]*=[[:space:]]*no/) bad = 1
        if (lcnc ~ /userknownhostsfile[[:space:]]*=[[:space:]]*\/dev\/null/) bad = 1
      }
    }
    END {
      if (!saw_ansible) exit 1
      if (bad)          exit 0
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
