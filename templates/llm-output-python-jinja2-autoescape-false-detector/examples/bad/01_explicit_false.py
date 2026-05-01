# BAD: explicit autoescape=False on an Environment whose loader serves HTML.
import jinja2

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"),
    autoescape=False,
)

def render_user(name):
    return env.get_template("greeting.html").render(name=name)
