# BAD: Template(..., autoescape=False) on an inline HTML body.
from jinja2 import Template

html_src = "<p>Hi {{ name }}</p>"
tpl = Template(html_src, autoescape=False)

def render(name):
    return tpl.render(name=name)
