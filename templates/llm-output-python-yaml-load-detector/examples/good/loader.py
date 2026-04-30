# Safe fixtures. Detector must NOT flag any line in this file.
import yaml
import yaml as Y
from yaml import SafeLoader

# safe_load — the canonical safe entry point.
def g1(stream):
    return yaml.safe_load(stream)

# Explicit SafeLoader.
def g2(stream):
    return yaml.load(stream, Loader=yaml.SafeLoader)

# Explicit CSafeLoader.
def g3(stream):
    return yaml.load(stream, Loader=yaml.CSafeLoader)

# BaseLoader (no implicit type resolution; safe).
def g4(stream):
    return yaml.load(stream, Loader=yaml.BaseLoader)

# Aliased import + SafeLoader.
def g5(stream):
    return Y.load(stream, Loader=Y.SafeLoader)

# Bare SafeLoader name in scope.
def g6(stream):
    return yaml.load(stream, Loader=SafeLoader)

# Suppression marker (audited legacy path).
def g7(stream):
    return yaml.load(stream)  # llm-allow:python-yaml-load-unsafe

# Comment containing fake call must not fire.
# yaml.load(stream)

# String literal containing the call shape must not fire.
EXAMPLE = "yaml.load(stream)  # bad"

# Different module — json.load is unrelated.
import json
def g8(stream):
    return json.load(stream)
