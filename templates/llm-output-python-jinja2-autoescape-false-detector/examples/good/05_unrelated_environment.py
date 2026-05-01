# GOOD: file references jinja2 in a comment but uses a different
# Environment class entirely (e.g. Django's). The detector should not
# flag the unrelated Environment(...) call.
#
# Note: we keep the word jinja2 in the docstring so the detector's
# anchor would still trigger; the test is that the Django Environment
# call (no FileSystemLoader, no .html string, no autoescape kwarg)
# is correctly judged as "not HTML context" and skipped.
"""Migration from jinja2 to django templates."""

from django.template import Engine as Environment

engine = Environment(dirs=["legacy"], debug=False)
