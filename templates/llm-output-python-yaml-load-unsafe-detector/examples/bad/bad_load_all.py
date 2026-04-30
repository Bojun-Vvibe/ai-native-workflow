"""Multi-doc unsafe load."""
import yaml

for doc in yaml.load_all(open("multi.yml")):
    print(doc)
