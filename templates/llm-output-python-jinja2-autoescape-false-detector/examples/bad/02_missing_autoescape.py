# BAD: jinja2 Environment with no autoescape= at all on an HTML loader.
# Jinja2's library default is autoescape=False; the absence is the bug.
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("views"))

def page(user_html):
    return env.get_template("index.html").render(content=user_html)
