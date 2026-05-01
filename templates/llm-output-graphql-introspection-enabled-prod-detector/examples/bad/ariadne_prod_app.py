# Ariadne production app. introspection=True passed explicitly even though
# DEBUG = False is set right above.
from ariadne import make_executable_schema
from ariadne.asgi import GraphQL

DEBUG = False

schema = make_executable_schema(type_defs, resolvers)

app = GraphQL(schema, debug=False, introspection=True)
