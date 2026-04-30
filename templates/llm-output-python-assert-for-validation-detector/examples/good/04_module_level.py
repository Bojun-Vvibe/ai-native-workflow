"""Good: top-level assert (typically a static-analyser hint).

Module-level asserts are not flagged because they are not part of
a function body and the typical use is to assert a constant
property at import time.
"""
import sys

assert sys.version_info >= (3, 8), "this module needs Python 3.8+"
