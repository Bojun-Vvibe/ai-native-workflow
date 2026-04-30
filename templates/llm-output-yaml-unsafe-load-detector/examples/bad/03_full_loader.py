import yaml

def parse(s):
    # FullLoader still permits python/name tags
    return yaml.load(s, Loader=yaml.FullLoader)
