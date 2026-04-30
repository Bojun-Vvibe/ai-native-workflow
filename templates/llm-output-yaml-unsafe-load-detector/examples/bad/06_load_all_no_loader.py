import yaml

def parse(stream):
    return list(yaml.load_all(stream))
