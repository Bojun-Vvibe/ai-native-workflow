import yaml
from yaml import CSafeLoader

def parse(s):
    return yaml.load(s, Loader=CSafeLoader)
