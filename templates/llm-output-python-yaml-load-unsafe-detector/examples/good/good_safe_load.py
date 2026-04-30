"""safe_load and safe_load_all are fine."""
import yaml

cfg = yaml.safe_load(open("config.yml"))
for doc in yaml.safe_load_all(open("multi.yml")):
    print(doc)
