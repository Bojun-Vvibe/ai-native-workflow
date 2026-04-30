"""Docstring example demonstrating ``mark_safe(user_input)`` is bad.

Code in this module never calls mark_safe at runtime; only the
docstring mentions it.
"""

def render(value):
    return value
