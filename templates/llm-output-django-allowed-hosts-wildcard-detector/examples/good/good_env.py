import os

# Environment-driven, validated upstream.
ALLOWED_HOSTS = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")
