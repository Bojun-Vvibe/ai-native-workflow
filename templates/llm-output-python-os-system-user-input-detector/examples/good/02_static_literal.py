# Good: plain string-literal arg with no interpolation. Outside this
# detector's scope (a different detector covers shell=True / static
# command best-practice). Notably `os.system("...")` here has zero
# attacker-controlled bytes.
import os


def show_uptime() -> int:
    return os.system("uptime")
