import os

# os.getenv with a default placeholder is treated as a fallback, not
# the canonical key, so it is intentionally NOT flagged.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "fallback-only-for-tests")
