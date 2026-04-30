# Bad: f-string interpolation directly into os.system.
import os


def ping(host):
    os.system(f"ping -c 1 {host}")


if __name__ == "__main__":
    ping("example.test; rm -rf /tmp/x")
