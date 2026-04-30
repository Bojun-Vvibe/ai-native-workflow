"""Explicit unsafe Loader."""
import yaml

doc = yaml.load(open("payload.yml"), Loader=yaml.Loader)
