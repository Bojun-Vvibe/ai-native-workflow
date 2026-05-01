# BAD: autoescape explicitly set to 0 (which is falsey).
import jinja2

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("ui"),
    autoescape=0,
)
