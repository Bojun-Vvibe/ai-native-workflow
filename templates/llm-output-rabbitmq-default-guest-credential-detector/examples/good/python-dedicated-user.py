# Production-shaped client: dedicated user, secret pulled from env.
import os
import pika

creds = pika.PlainCredentials(
    os.environ["RABBIT_USER"],
    os.environ["RABBIT_PASSWORD"],
)
params = pika.ConnectionParameters(
    host=os.environ["RABBIT_HOST"],
    port=5672,
    virtual_host="/jobs",
    credentials=creds,
    ssl_options=None,  # set in real prod
)
conn = pika.BlockingConnection(params)
conn.close()
