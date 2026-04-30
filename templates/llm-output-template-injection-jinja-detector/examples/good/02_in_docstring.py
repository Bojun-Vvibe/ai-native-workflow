# This file mentions render_template_string("hi " + x) inside a docstring
# but never actually calls it.
"""
Do not write code like:
    return render_template_string("hi " + x)
because that is dynamic.
"""

def safe():
    return "ok"
