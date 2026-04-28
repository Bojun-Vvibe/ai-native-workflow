import re

PAT_SAFE = re.compile(r"^[a-z0-9_]+$")
EMAIL_OK = re.compile(r"^[\w.+-]+@example\.com$")
WORDS = re.compile(r"\b\w+\b")


def check(s):
    return PAT_SAFE.match(s) and EMAIL_OK.fullmatch(s) and WORDS.findall(s)
