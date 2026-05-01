# Pythonic example: amqp URI hands guest:guest to a remote broker.
import pika

params = pika.URLParameters("amqp://guest:guest@broker.internal.example.com:5672/")
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.queue_declare(queue="jobs")
ch.basic_publish(exchange="", routing_key="jobs", body=b"hello")
conn.close()
