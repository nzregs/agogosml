"""Kafka streaming client"""

from confluent_kafka import Producer, Consumer, admin
from confluent_kafka import KafkaException, KafkaError
import datetime
from .abstract_streaming_client import AbstractStreamingClient
from ..utils.logger import Logger

logger = Logger()


class KafkaStreamingClient(AbstractStreamingClient):
    def __init__(self, config):
        """
        Class to create a KafkaStreamingClient instance.

        :param config: Dictionary file with all the relevant parameters.
        :param topic: A string kafka topic.
        """

        self.topic = config.get("KAFKA_TOPIC")
        if config.get("TIMEOUT"):
            try:
                self.timeout = int(config.get("TIMEOUT"))
            except ValueError:
                self.timeout = None
        else:
            self.timeout = None

        kafka_config = self.create_kafka_config(config)
        self.admin = admin.AdminClient(kafka_config)

        if config.get("KAFKA_CONSUMER_GROUP") is None:
            self.producer = Producer(kafka_config)
        else:
            self.app_host = config.get("APP_HOST")
            self.app_port = config.get("APP_PORT")
            self.consumer = Consumer(kafka_config)

    @staticmethod
    def create_kafka_config(user_config):

        config = {
            "bootstrap.servers": user_config.get("KAFKA_ADDRESS"),
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest"
        }

        consumer_group = user_config.get("KAFKA_CONSUMER_GROUP")
        if consumer_group is not None:
            config["group.id"] = consumer_group

        return config

    def delivery_report(self, err, msg):
        """ Called once for each message produced to indicate delivery result.
        Triggered by poll() or flush().

        :param err: An error message.
        :param msg: A string input to be uploaded to kafka.
        """

        if err is not None:
            logger.error('Message delivery failed: {}'.format(err))
        else:
            logger.info('Message delivered to {} [{}]'.format(
                msg.topic(), msg.partition()))

    def send(self, message: str, *args, **kwargs):
        """
        Upload a message to a kafka topic.

        :param message: A string input to upload to kafka.
        """
        if not isinstance(message, str):
            raise TypeError('str type expected for message')
        mutated_message = message.encode('utf-8')
        self.producer.poll(0)
        self.producer.produce(
            self.topic, mutated_message, callback=self.delivery_report)
        self.producer.flush()

    def stop(self, *args, **kwargs):
        pass

    def check_timeout(self, start):
        """
        Checks how much time has elapsed since the kafka client started running.

        :param start: Start time.
        """
        if self.timeout is not None:
            elapsed = datetime.datetime.now() - start
            if elapsed.seconds >= self.timeout:
                raise KeyboardInterrupt

    def handle_kafka_error(self, msg):
        """
        Handle an error in kafka.

        :param msg: Error message from kafka.
        """
        if msg.error().code() == KafkaError._PARTITION_EOF:
            # End of partition event
            logger.error('%% %s [%d] reached end at offset %d\n' %
                         (msg.topic(), msg.partition(), msg.offset()))
        else:
            # Error
            raise KafkaException(msg.error())

    def start_receiving(self, on_message_received_callback):
        """
        Receive messages from a kafka topic.

        :param on_message_received_callback: Callback function.
        """
        '''
        TODO:
        We are going to need documentation for Kafka
        to ensure proper syntax is clear
        '''
        try:
            self.consumer.subscribe([self.topic])
            start = datetime.datetime.now()

            while True:
                # Stop loop after timeout if exists
                self.check_timeout(start)

                # Poll messages from topic
                msg = self.consumer.poll(0.00000001)
                if msg is None:
                    continue
                if msg.error():
                    # Error or event
                    self.handle_kafka_error(msg)
                else:
                    # Proper message
                    on_message_received_callback(msg.value())
                    self.consumer.commit(msg)

        except KeyboardInterrupt:
            logger.info('Aborting listener...')

        finally:
            # Close down consumer to commit final offsets.
            self.consumer.close()
