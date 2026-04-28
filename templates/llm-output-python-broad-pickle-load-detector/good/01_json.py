import json


def load_blob(path):
    with open(path, "r") as f:
        return json.load(f)  # safe alternative
