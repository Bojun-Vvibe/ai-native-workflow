"""UnsafeLoader is by-name a giveaway."""
import yaml

data = yaml.load(payload, Loader=yaml.UnsafeLoader)
