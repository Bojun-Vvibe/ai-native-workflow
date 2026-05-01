# Production-named module that hardcodes DEBUG=True with no env
# var lookup anywhere — the worst case.
from .base import *  # noqa

SECRET_KEY = "REPLACE_ME_FAKE_KEY_NOT_REAL"
DEBUG = True
ALLOWED_HOSTS = ["api.example.com"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "appdb",
        "USER": "appuser",
        "PASSWORD": "REPLACE_ME_FAKE_PASSWORD",
        "HOST": "db.internal",
        "PORT": 5432,
    }
}
