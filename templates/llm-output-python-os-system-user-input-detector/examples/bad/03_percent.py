# Bad: %-formatting, the printf-style legacy shape.
import os


def show(user):
    os.system("id %s" % user)
