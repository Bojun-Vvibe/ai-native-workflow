import re

PAT_DOTSTAR = re.compile("(.*)*")
PAT_NESTED = re.compile(r"(a+)+")
EMAIL_BAD = re.compile(r"^([\w.+-]+)+@example\.com$")


def check(s):
    return PAT_DOTSTAR.match(s) and PAT_NESTED.search(s) and EMAIL_BAD.fullmatch(s)
