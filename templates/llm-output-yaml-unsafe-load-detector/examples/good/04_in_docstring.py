"""Module docstring that mentions yaml.load(s) as a common
mistake to avoid. The string yaml.unsafe_load(x) appears here too,
but neither is an actual call.
"""
import yaml

def parse(s):
    return yaml.safe_load_all(s)
