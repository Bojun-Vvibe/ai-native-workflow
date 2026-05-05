# superset_config.py — bad: PUBLIC_ROLE_LIKE resolved from env with a
# non-empty default of "Gamma". An out-of-the-box deployment that
# does not set SUPERSET_PUBLIC_ROLE will silently grant anonymous
# visitors the Gamma role's permissions.
import os
PUBLIC_ROLE_LIKE = os.environ.get("SUPERSET_PUBLIC_ROLE", "Gamma")
