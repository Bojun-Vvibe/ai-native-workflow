# sentry.conf.py -- self-hosted Sentry settings
# upstream: getsentry/sentry

import os
from sentry.conf.server import *  # noqa

DATABASES = {
    "default": {
        "ENGINE": "sentry.db.postgres",
        "NAME": "sentry",
        "USER": "sentry",
        "HOST": "postgres",
        "PORT": "5432",
    }
}

SECRET_KEY = os.environ["SENTRY_SECRET_KEY"]

SENTRY_OPTIONS = {}
