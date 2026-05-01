# GOOD: Environment with autoescape=True and a custom loader.
import jinja2

env = jinja2.Environment(
    loader=jinja2.PackageLoader("myapp", "templates"),
    autoescape=True,
    trim_blocks=True,
)
