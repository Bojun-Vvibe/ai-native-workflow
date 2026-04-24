"""Worked example: redact a realistic tool-call result before re-prompting the model.

Three scenarios:
  1. `ls -la` style filesystem listing  -> home paths get redacted
  2. `curl` debug output                -> bearer token + email get redacted
  3. Repeated mention                   -> stable token across reappearances
"""

from __future__ import annotations

from redactor import Redactor


SCENARIO_1_LS_OUTPUT = """\
total 24
-rw-r--r--  1 alice  staff  120 Apr  1 09:00 /home/alice/projects/svc/config.yaml
-rw-r--r--  1 alice  staff   88 Apr  1 09:01 /home/alice/projects/svc/.env
drwxr-xr-x  3 alice  staff   96 Apr  1 09:02 /home/alice/projects/svc/src
"""

SCENARIO_2_CURL_OUTPUT = """\
> GET /v1/users HTTP/1.1
> Host: api.example.com
> Authorization: Bearer xoxp-FAKE-EXAMPLE-TOKEN-do-not-use-1234567890
< HTTP/1.1 200 OK
{"id":42,"email":"alice@example.com","admin_email":"ops@example.com"}
"""

SCENARIO_3_REPEAT = """\
Connecting to db at 10.0.5.42 ... ok
Replicating from 10.0.5.42 to 10.0.5.43 ... ok
Verified primary 10.0.5.42 is healthy.
"""


def show(label: str, original: str) -> None:
    r = Redactor()  # per-call scope
    redacted, report = r.redact(original)
    print(f"=== {label} ===")
    print("--- original ---")
    print(original.rstrip())
    print("--- redacted ---")
    print(redacted.rstrip())
    print(f"--- {report} ---")
    print()


if __name__ == "__main__":
    show("scenario 1: filesystem listing", SCENARIO_1_LS_OUTPUT)
    show("scenario 2: curl debug",          SCENARIO_2_CURL_OUTPUT)
    show("scenario 3: repeated IP",         SCENARIO_3_REPEAT)

    # Demonstrate idempotency: redacting the redacted text is a no-op.
    r = Redactor()
    once, _ = r.redact(SCENARIO_2_CURL_OUTPUT)
    twice, report2 = Redactor().redact(once)
    print("=== idempotency check ===")
    print(f"redact(redact(x)) == redact(x): {once == twice}")
    print(f"second-pass report: {report2}")
