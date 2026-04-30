"""FullLoader is still vulnerable to !!python/object/new (CVE-2020-14343)."""
import yaml

config = yaml.load(stream, Loader=yaml.FullLoader)
