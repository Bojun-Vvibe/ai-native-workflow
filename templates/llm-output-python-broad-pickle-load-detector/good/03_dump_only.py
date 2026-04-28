import pickle


def dump_only(obj, path):
    # We only WRITE pickle here — dumping is not a deserialization risk.
    with open(path, "wb") as f:
        pickle.dump(obj, f)
