# superset_config.py — bad: PUBLIC_ROLE_LIKE bound to Admin. Anonymous
# visitors of the Superset UI inherit full administrator permissions
# on the next `superset init` run.
SECRET_KEY = "change-me-in-prod-please"
PUBLIC_ROLE_LIKE = "Admin"
