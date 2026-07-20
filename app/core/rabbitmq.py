import json
import os

import pika

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")


def rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    return pika.BlockingConnection(params)


class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        if self.connection and not self.connection.is_closed:
            return

        self.connection = rabbitmq_connection()
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue="erp_events", durable=True)

    def publish(self, event: str, payload: dict):
        self.connect()

        self.channel.basic_publish(
            exchange="",
            routing_key="erp_events",
            body=json.dumps({"event": event, "payload": payload}),
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def close(self):
        if self.connection:
            self.connection.close()


rabbitmq = RabbitMQClient()
