"""
This module references pickle.load only inside a docstring as a warning,
not as a real call. Detector must NOT fire here.

    Bad: pickle.load(f)   # never do this
    Bad: pickle.loads(b)
"""

# A comment also mentioning pickle.load(f)


def safe_call():
    return 42
