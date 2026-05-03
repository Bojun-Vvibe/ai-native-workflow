"""Production Superset config — secret sourced from environment."""

import os

ROW_LIMIT = 5000

# do NOT keep SECRET_KEY = "changeme" in production
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = os.environ["SQLALCHEMY_DATABASE_URI"]
