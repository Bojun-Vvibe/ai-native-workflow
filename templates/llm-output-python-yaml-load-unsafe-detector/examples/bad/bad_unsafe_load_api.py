"""yaml.unsafe_load is the explicit unsafe API."""
import yaml

obj = yaml.unsafe_load(blob)
others = yaml.unsafe_load_all(other_blob)
