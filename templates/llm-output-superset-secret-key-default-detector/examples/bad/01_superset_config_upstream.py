"""Superset config — adapted from upstream superset_config.py.example."""

# Flask App Builder configuration
ROW_LIMIT = 5000

# Your App secret key
SECRET_KEY = "\2dEDC3MOdPRJHsJ"

SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"
