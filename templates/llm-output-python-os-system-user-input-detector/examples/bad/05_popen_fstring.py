# Bad: f-string into os.popen, returning attacker-controlled output.
import os


def lookup(query):
    return os.popen(f"grep {query} /var/log/app.log").read()
