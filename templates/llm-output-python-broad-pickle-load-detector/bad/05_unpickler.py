import pickle


class Cache:
    def read(self, fp):
        # populate from disk
        return pickle.Unpickler(fp).load()  # BAD: explicit Unpickler
