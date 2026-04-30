"""Ensure literals and suppressed lines do not trigger findings.

The string below contains the substring "tempfile.mktemp(" but
it lives inside a docstring, so it must not be flagged.
"""

import tempfile

# Documentation: tempfile.mktemp() in a comment must not flag.
NOTE = "tempfile.mktemp() would be wrong here"


def legacy_path() -> str:
    # Test fixture only — not used in production code paths.
    return tempfile.mktemp(suffix=".fixture")  # mktemp-ok
