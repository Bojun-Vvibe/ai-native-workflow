import yaml

def parse(s):
    # safe loader, no Python tag execution
    return yaml.safe_load(s)
