"""good: docstring and comments mention the dangerous names but never call them.

The detector must not be fooled by the strings:

    "ssl._create_unverified_context"
    "ctx.check_hostname = False"
    "verify_mode = ssl.CERT_NONE"

These are mentioned only as text, not as live code.
"""
import ssl

# Reminder: never write `ctx.check_hostname = False` in real code.
# Reminder: never write `ctx.verify_mode = ssl.CERT_NONE` either.
ctx = ssl.create_default_context()
print(ctx)
