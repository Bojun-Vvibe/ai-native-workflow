# Bad: str.format-style interpolation into os.popen.
import os


def list_dir(d):
    return os.popen("ls -la {}".format(d)).read()
