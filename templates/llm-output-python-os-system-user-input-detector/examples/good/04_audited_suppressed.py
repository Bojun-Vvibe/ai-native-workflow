# Good: deliberately-audited test fixture, suppressed via the audit comment.
# The path is a fixed test-only string under our control.
import os

FIXTURE = "/tmp/test-fixture-out"


def cleanup_fixture():
    os.system("rm -f " + FIXTURE)  # os-system-ok — fixed test-controlled path
