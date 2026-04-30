"""Explicit SafeLoader / CSafeLoader is fine."""
import yaml

a = yaml.load(stream, Loader=yaml.SafeLoader)
b = yaml.load(stream, Loader=yaml.CSafeLoader)
c = yaml.load_all(stream, Loader=yaml.SafeLoader)
