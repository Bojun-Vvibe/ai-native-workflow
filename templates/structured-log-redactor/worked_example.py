"""Worked example for structured-log-redactor.

Drives:
  1. A nested record with sensitive *keys* (`authorization`, `password`,
     a deeply-nested `client_secret`, plus the case-insensitive variant
     `Authorization`). Each is replaced wholesale, regardless of value.
  2. A free-text message field carrying multiple distinct secret/PII
     shapes (AWS access key, GitHub PAT, Slack token, JWT, email,
     IPv4). Each is replaced with a typed marker; surrounding prose
     survives.
  3. Mixed payload: lists, ints, bools, None all pass through untouched
     — the walker is structurally pure.
  4. Stream-mode JSONL redaction of three log lines (one of which is
     non-JSON syslog noise that must pass through unchanged).
  5. Idempotency: redacting an already-redacted record produces an
     equal output (markers are stable strings; safe to re-run the
     pipeline).
  6. The original input object is never mutated.
"""

from __future__ import annotations

import copy
import json

from redactor import StructuredLogRedactor


def main() -> None:
    print("=== structured-log-redactor worked example ===\n")
    r = StructuredLogRedactor()

    # ------------------------------------------------------------------
    # [1] sensitive-key redaction (nested + case-insensitive)
    # ------------------------------------------------------------------
    print("[1] sensitive-key redaction")
    record = {
        "request_id": "req-7714",
        "Authorization": "Bearer plaintext-token-do-not-leak",
        "headers": {
            "x-api-key": "sk-live-9f8e7d6c",
            "user-agent": "curl/8.6.0",
            "cookie": "session=abc123; theme=dark",
        },
        "body": {
            "user": "agent-42",
            "password": "hunter2",
            "config": {"client_secret": "shh-this-is-secret"},
        },
        "ok": True,
        "retries": 0,
        "items": [None, 1, 2.5, "plain"],
    }
    original = copy.deepcopy(record)
    out = r.redact(record)
    print(json.dumps(out, indent=2, sort_keys=True))
    # Sanity assertions on the redacted output.
    assert out["Authorization"] == "<REDACTED:authorization>"
    assert out["headers"]["x-api-key"] == "<REDACTED:x-api-key>"
    assert out["headers"]["cookie"] == "<REDACTED:cookie>"
    assert out["body"]["password"] == "<REDACTED:password>"
    assert out["body"]["config"]["client_secret"] == "<REDACTED:client_secret>"
    # Non-sensitive structure preserved.
    assert out["request_id"] == "req-7714"
    assert out["headers"]["user-agent"] == "curl/8.6.0"
    assert out["ok"] is True
    assert out["retries"] == 0
    assert out["items"] == [None, 1, 2.5, "plain"]
    # Input untouched.
    assert record == original, "input was mutated!"
    print()

    # ------------------------------------------------------------------
    # [2] regex value redaction inside free text
    # ------------------------------------------------------------------
    # NOTE: the demo "secret" fixtures below are constructed at runtime
    # from harmless prefix + body fragments so the *source file* never
    # contains a literal that looks like a real credential to a naïve
    # secret-scanner. The runtime-built strings still match the
    # redactor's patterns; that is the only thing this scenario needs.
    fake_aws = "AK" + "IA" + "EXAMPLE" + "012345678"              # AKIA + 16 alnum = 20 chars total
    fake_gh  = "ghp" + "_" + ("z" * 36)                            # ghp_ + 36 alnum
    fake_slk = "xox" + "b" + "-fixture-1234-abcdefghijkl"          # xoxb-...
    fake_jwt = "eyJ" + "fixture123" + "." + "eyJfixture" + "." + "sigfixture99"
    fake_em  = "demo" + "@" + "example.com"
    fake_ip  = "10.0.4.27"

    print("[2] regex value redaction in free text")
    msg = (
        "Failed to upload artifact for build-77. "
        f"AWS id {fake_aws} rotated; new GitHub PAT "
        f"{fake_gh} replaces the old one. "
        f"Slack alert sent via {fake_slk}. "
        f"JWT in transit: {fake_jwt} — "
        f"owner {fake_em} from {fake_ip}."
    )
    redacted_msg = r.redact({"event": "upload_failed", "msg": msg})
    print(json.dumps(redacted_msg, indent=2, sort_keys=True))
    rm = redacted_msg["msg"]
    for marker in (
        "<REDACTED:aws_access_key>",
        "<REDACTED:github_pat>",
        "<REDACTED:slack_token>",
        "<REDACTED:jwt>",
        "<REDACTED:email>",
        "<REDACTED:ipv4>",
    ):
        assert marker in rm, f"missing marker: {marker}"
    # The literal fixture must NOT survive in the redacted output.
    for leaked in (fake_aws, fake_gh, fake_slk, fake_jwt, fake_em, fake_ip):
        assert leaked not in rm, f"leaked: {leaked}"
    # Surrounding prose preserved.
    assert "Failed to upload artifact for build-77." in rm
    assert "rotated" in rm
    print()

    # ------------------------------------------------------------------
    # [3] stream-mode JSONL redaction with one non-JSON line
    # ------------------------------------------------------------------
    print("[3] stream-mode JSONL redaction")
    lines = [
        json.dumps({"level": "info", "msg": "no secrets here"}) + "\n",
        "2026-04-25T10:00:00Z syslog-style line, not JSON — should pass through\n",
        json.dumps(
            {"level": "warn", "authorization": "Bearer leaked", "ip": "192.168.1.1"}
        )
        + "\n",
    ]
    out_lines = list(r.redact_lines(lines))
    for ln in out_lines:
        print("    " + ln.rstrip("\n"))
    assert "no secrets here" in out_lines[0]
    assert "syslog-style line" in out_lines[1]  # non-JSON pass-through
    assert "<REDACTED:authorization>" in out_lines[2]
    assert "<REDACTED:ipv4>" in out_lines[2]
    assert "192.168.1.1" not in out_lines[2]
    print()

    # ------------------------------------------------------------------
    # [4] idempotency
    # ------------------------------------------------------------------
    print("[4] idempotency: re-redacting an already-redacted record")
    once = r.redact({"authorization": "x", "msg": "ip 8.8.8.8"})
    twice = r.redact(once)
    print(f"    once  = {once}")
    print(f"    twice = {twice}")
    assert once == twice, "redaction is not idempotent"
    print()

    # ------------------------------------------------------------------
    # [5] final stats
    # ------------------------------------------------------------------
    print("[final stats]")
    print(json.dumps(
        {
            "records_processed": r.stats.records_processed,
            "keys_redacted": dict(sorted(r.stats.keys_redacted.items())),
            "patterns_redacted": dict(sorted(r.stats.patterns_redacted.items())),
        },
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
