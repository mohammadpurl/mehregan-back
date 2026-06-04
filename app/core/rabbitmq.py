import pika
import json


class RabbitMQClient:
    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        if self.connection and not self.connection.is_closed:
            return

        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host="localhost")
        )
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


# 👇 این دقیقاً همان چیزی است که import می‌کنی
rabbitmq = RabbitMQClient()
