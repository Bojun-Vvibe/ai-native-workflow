import yaml

def parse(s):
    return yaml.load(s, Loader=yaml.SafeLoader)
