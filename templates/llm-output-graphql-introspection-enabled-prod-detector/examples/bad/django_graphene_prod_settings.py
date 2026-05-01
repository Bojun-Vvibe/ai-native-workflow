# Django settings module for production. graphene-django introspection is
# left on, exposing the full schema to anonymous clients.
DEBUG = False
ALLOWED_HOSTS = ["api.example.com"]

GRAPHENE = {
    "SCHEMA": "myapp.schema.schema",
    "INTROSPECTION": True,
}
