import yaml
from yaml import Loader

def parse(s):
    return yaml.load(s, Loader=Loader)
