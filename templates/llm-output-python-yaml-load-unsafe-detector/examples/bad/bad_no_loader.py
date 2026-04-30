"""LLM reflex: no Loader= → unsafe pre-5.1 default."""
import yaml

with open("config.yml") as fh:
    cfg = yaml.load(fh)

print(cfg)
