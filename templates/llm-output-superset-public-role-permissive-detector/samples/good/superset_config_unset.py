# superset_config.py — good: PUBLIC_ROLE_LIKE not mentioned at all.
# The default behaviour leaves the Public role with no permissions.
SECRET_KEY = "rotated-by-secret-manager"
SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://superset:***@db/superset"
WTF_CSRF_ENABLED = True
