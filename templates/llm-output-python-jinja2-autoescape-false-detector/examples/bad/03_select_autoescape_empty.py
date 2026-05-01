# BAD: select_autoescape([]) — empty list means "never autoescape".
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape([]),
)
