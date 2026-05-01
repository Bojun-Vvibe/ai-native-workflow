# Local dev: guest URI but only against loopback. Acceptable per the
# upstream RabbitMQ documentation -- guest is loopback-only by default.
import pika

params = pika.URLParameters("amqp://guest:guest@127.0.0.1:5672/")
conn = pika.BlockingConnection(params)
ch = conn.channel()
ch.queue_declare(queue="jobs")
conn.close()
