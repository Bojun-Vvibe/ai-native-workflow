from pickle import loads


def deserialize(b):
    return loads(b)  # BAD: bare loads
