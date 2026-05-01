# Generated settings.py snippet — basic hardcoded SECRET_KEY.
import os

DEBUG = False
ALLOWED_HOSTS = ["example.test"]

SECRET_KEY = "django-insecure-9!*8z@kq^mz5p$3w&2yvf+1abc"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join("/tmp", "db.sqlite3"),
    }
}
