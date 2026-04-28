import pickle


def load_blob(path):
    with open(path, "rb") as f:
        return pickle.load(f)  # BAD
