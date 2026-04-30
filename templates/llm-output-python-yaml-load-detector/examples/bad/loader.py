# Fixtures for the unsafe yaml.load detector. These are intentionally
# vulnerable patterns the detector must flag. They are NOT exploits —
# no payloads, no untrusted IO targets, just the call shape.
import yaml
import yaml as Y
import yaml as myyaml

# Finding 1: bare yaml.load.
def f1(stream):
    return yaml.load(stream)

# Finding 2: yaml.load_all.
def f2(stream):
    return list(yaml.load_all(stream))

# Finding 3: yaml.load with FullLoader (still unsafe — pre-5.1 behavior).
def f3(stream):
    return yaml.load(stream, Loader=yaml.FullLoader)

# Finding 4: yaml.load with explicit yaml.Loader (the unsafe one).
def f4(stream):
    return yaml.load(stream, Loader=yaml.Loader)

# Finding 5: aliased import.
def f5(stream):
    return Y.load(stream)

# Finding 6: aliased import with load_all.
def f6(stream):
    return list(myyaml.load_all(stream))

# Finding 7: yaml.load on file handle.
def f7(path):
    with open(path) as fh:
        return yaml.load(fh)

# Finding 8: multi-line call form, no Loader at all.
def f8(stream):
    return yaml.load(
        stream,
    )
