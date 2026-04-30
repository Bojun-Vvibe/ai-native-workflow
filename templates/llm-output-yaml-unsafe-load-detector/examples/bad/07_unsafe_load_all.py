import yaml

def parse(stream):
    return list(yaml.unsafe_load_all(stream))
