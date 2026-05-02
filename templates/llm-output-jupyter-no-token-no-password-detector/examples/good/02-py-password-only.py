# Hashed password set; token may be empty (Jupyter accepts either).
c = get_config()
c.ServerApp.token = ''
c.ServerApp.password = 'argon2:$argon2id$v=19$m=10240,t=10,p=8$abc...'
