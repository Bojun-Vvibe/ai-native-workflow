# Bad: classic string concatenation.
import os


def archive(path):
    os.system("tar czf /tmp/out.tgz " + path)
