"""This docstring contains literal-looking calls like
Fernet(b"AAAA") and AES.new(b"abcd", mode) but they live inside a
string and must NOT be flagged.
"""
def doc_only():
    s = 'Fernet(b"in-a-string-literal")'
    return s
