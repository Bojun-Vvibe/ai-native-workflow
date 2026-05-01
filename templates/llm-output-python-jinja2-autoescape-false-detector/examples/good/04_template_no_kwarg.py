# GOOD: jinja2 Template() with no autoescape kwarg — we only flag when
# autoescape= is explicitly set to a falsey value, because for a bare
# Template() (no HTML loader, no .html string), defaulting to off is
# acceptable for non-HTML use (e.g. SQL fragment templating).
from jinja2 import Template

tpl = Template("SELECT {{ col }} FROM t WHERE id = {{ id }}")

def render(col, id_):
    return tpl.render(col=col, id=id_)
