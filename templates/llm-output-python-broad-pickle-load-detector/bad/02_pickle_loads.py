import pickle


def from_bytes(buf):
    return pickle.loads(buf)  # BAD
