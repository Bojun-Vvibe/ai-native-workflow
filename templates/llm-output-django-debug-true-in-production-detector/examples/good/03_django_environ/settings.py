import environ

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env()

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["app.example.com"])
