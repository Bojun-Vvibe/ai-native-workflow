import os

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = ["api.example.invalid", "www.example.invalid"]
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
