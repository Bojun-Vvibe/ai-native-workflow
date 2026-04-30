import yaml

def load_config(path):
    with open(path) as fh:
        return yaml.load(fh)
