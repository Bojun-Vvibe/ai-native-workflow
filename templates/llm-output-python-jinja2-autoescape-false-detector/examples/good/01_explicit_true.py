# GOOD: autoescape=True explicitly.
import jinja2

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=True,
)
