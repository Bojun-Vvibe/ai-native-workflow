# BAD: lambda-style autoescape that always returns False.
import jinja2

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=lambda name: False,
)
