import pickle as p


def restore(stream):
    return p.load(stream)  # BAD: alias
