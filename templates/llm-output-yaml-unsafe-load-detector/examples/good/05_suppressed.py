import yaml

def parse(s):
    return yaml.load(s, Loader=yaml.FullLoader)  # yaml-load-ok: trusted source
