# jupyter_server_config.py — token from env, password unset
import os
c = get_config()
c.ServerApp.token = os.environ['JUPYTER_TOKEN']
c.ServerApp.ip = '127.0.0.1'
