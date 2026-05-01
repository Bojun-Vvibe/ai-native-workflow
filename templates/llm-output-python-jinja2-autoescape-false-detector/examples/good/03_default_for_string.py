# GOOD: select_autoescape with default_for_string=True.
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("ui"),
    autoescape=select_autoescape(default_for_string=True, default=True),
)
