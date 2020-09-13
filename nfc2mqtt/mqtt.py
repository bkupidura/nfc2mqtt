import time
import socket
import logging
import json

import paho.mqtt.client as paho

LOG = logging.getLogger(__name__)

class Mqtt(object):

    def __init__(self):
        super(Mqtt, self).__init__()
        self.publish_queue = list()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            LOG.info('Connection to broker established')
            for topic in userdata.get('subscribe_to', list()):
                self.mqtt.subscribe(topic)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            LOG.error('Connection to broker failed, reconnecting (paho rc %d)', rc)
            while True:
                try:
                    self.mqtt.reconnect()
                except socket.error:
                    time.sleep(2)
                else:
                    break

    def _connect(self, server, port, keepalive, retries=-1):
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        while retries != 0:
            try:
                self.mqtt.connect(server, port, keepalive)
            except socket.error:
                retries -= 1
                LOG.error('Fail to connect to broker, waiting..')
                time.sleep(2)
            else:
                break

    def connect(self, subscribe_to=None):
        LOG.info('Connecting to mqtt broker: %s', self.mqtt_config)

        userdata = dict()
        if subscribe_to is not None:
            userdata['subscribe_to'] = subscribe_to

        self.mqtt = paho.Client(userdata=userdata, protocol=paho.MQTTv31)

        if self.mqtt_config['username'] is not None:
            self.mqtt.username_pw_set(self.mqtt_config['username'], self.mqtt_config['password'])

        self._connect(self.mqtt_config['server'], self.mqtt_config['port'], self.mqtt_config['keepalive'])

    def loop_start(self):
        self.mqtt.loop_start()

    def resend_publish_queue(self):
        publish_queue_len = len(self.publish_queue)
        for _ in range(publish_queue_len):
            topic, payload = self.publish_queue.pop(0)
            self.publish(topic, payload)

    def publish(self, topic=None, payload=None):
        if self.mqtt._host:
            if topic is not None:
                if isinstance(payload, dict) or isinstance(payload, list):
                    payload = json.dumps(payload)
                status = self.mqtt.publish(topic, payload=payload)
                if status.rc != 0:
                    LOG.error('Unable to publish message (paho rc %d). Adding message to queue', status.rc)
                    self.publish_queue.append((topic, payload))
            else:
                LOG.warning('Publish topic is empty')
        else:
            LOG.error('Unable to publish message to %s, client is not connected to broker. Adding message to queue', topic)
            self.publish_queue.append((topic, payload))
