"""Docstring with a literal-looking call:
    jwt.decode(token, key, verify=False)
that lives inside a string and must NOT be flagged.
"""
def doc_only():
    s = 'jwt.decode(token, key, algorithms=["none"])'
    return s
