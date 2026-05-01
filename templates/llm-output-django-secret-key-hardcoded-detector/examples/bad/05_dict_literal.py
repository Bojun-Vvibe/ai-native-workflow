# Sometimes settings are shipped as a dict and merged into globals().
DJANGO_SETTINGS = {
    "DEBUG": False,
    "SECRET_KEY": "literally-hardcoded-in-a-dict",
    "ALLOWED_HOSTS": ["*"],
}
