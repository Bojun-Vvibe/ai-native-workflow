# GOOD: select_autoescape(['html', 'htm']) — recommended idiom.
from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "htm"]),
)
