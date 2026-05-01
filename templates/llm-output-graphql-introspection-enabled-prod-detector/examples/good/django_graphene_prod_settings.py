# Django prod settings that explicitly disable graphene introspection.
DEBUG = False
ALLOWED_HOSTS = ["api.example.com"]

GRAPHENE = {
    "SCHEMA": "myapp.schema.schema",
    "INTROSPECTION": False,
}
