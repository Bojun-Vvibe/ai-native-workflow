# jupyter-open-allowed
# Air-gapped scratch container — auth disabled is intentional.
c = get_config()
c.ServerApp.token = ''
c.ServerApp.password = ''
