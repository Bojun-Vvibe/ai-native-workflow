"""yaml.load mentioned only in strings/comments, plus suppressed line."""
# Discussion: do not use yaml.load(stream); prefer yaml.safe_load.
docstring = "Avoid yaml.load(stream, Loader=yaml.Loader) in production."
note = 'yaml.unsafe_load is unsafe by name'

# In-process round-trip of internally generated data is fine.
import yaml
trusted = yaml.load(internally_dumped, Loader=yaml.Loader)  # yaml-unsafe-ok
