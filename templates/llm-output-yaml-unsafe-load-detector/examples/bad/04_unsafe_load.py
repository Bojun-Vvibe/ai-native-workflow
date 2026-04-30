import yaml

def parse(s):
    return yaml.unsafe_load(s)
