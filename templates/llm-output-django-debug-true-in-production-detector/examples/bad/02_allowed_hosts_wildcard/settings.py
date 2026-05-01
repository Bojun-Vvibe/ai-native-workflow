# LLM "fix" for `DisallowedHost at /`: just allow everything.
import os
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = ['*']
