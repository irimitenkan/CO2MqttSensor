'''
Created on 18.11.2023

@author: irimi
'''

import paho.mqtt.client as mqtt
from paho.mqtt.client import connack_string as conn_ack
import signal
import logging
import time
import socket
import ssl
import json

"""
QOS: 0 => fire and forget A -> B
QOS: 1 => at leat one - msg will be send
          (A) since publish_ack (B) is not received
QOS: 3 => exactly once :
          Publish (A) -> PubRec (B) -> PUBREL (A) -> PUBCOM (B) -> A
"""
QOS = 1

""" True: MSG is stored at Broker and keeps available for new subscribes,
    False: new publish required after subscribes
"""
RETAIN = True

# hostname = socket.gethostname()
HASS_DISCOVERY_PREFIX = 'homeassistant'


def encode_json(value) -> str:
    return json.dumps(value)


class MQTTClient (mqtt.Client):
    """ MQTT client class """

    def __init__(self, cfg, ClientID) -> None:
        super().__init__(ClientID)
        self.SensorValues = dict()
        self.SensorConfigs = dict()

        #self._client_id = ClientID
        self.cfg = cfg
        self._mqtt_client = None
        self._disconnectRQ = False
        self._avTopics = dict()
        self._stTopics = dict()
        self._hassTopics = dict()
        self._hostname = socket.gethostname()

        self._baseTopic = f"{ClientID}/{self._hostname}"
        signal.signal(signal.SIGINT, self.daemon_kill)
        signal.signal(signal.SIGTERM, self.daemon_kill)
        self._ONLINE_STATE = f"{self._baseTopic}/online"
        self.setupDevices()

    def setupDevices(self):
        """
        setup device specific sensors
        to be implemented by derived class 
        """
        pass

    def poll(self):
        """
        poll data from connected device
        to be implemented by derived class 
        """
        pass

    # def subsribe_topics(self):
    #     """
    #     subscribe for topics from MQTT broker
    #     to be implemented by derived class
    #     """
    #     pass

    def _setupSensorTopics(self, sensors: list):
        """
        build all required sensor topics and init sensor values
        """
        # init sensor values
        self.SensorValues = dict(zip(sensors, [0] * len(sensors)))
        # for idx, tp in enumerate(sensors, 1):
        for tp in sensors:
            self._avTopics[tp] = f"{self._baseTopic}/{tp}/available"
            self._stTopics[tp] = f"{self._baseTopic}/{tp}"
            self._hassTopics[tp] = f"{HASS_DISCOVERY_PREFIX}/sensor/{socket.gethostname()}/{tp}sensor/config"

    def daemon_kill(self, *_args):
        self.client_down()
        logging.info(f"{self._client_id} MQTT daemon Goodbye!")
        exit(0)

    def on_connect(self, _client, _userdata, _flags, rc):
        """
        on_connect when MQTT CleanSession=False (default) conn_ack will be send from broker
        """
        logging.debug(f"Connection returned result: {conn_ack(rc)}")
        self.publish(self._ONLINE_STATE, True, RETAIN)
        time.sleep(1)
        self.publish_hass()
        self.publish_avail_topics()
        time.sleep(1)
        self.publish_state_topics()

    def publish_avail_topics(self, avail=True):
        """ publish all available topics """
        for t in self._avTopics:
            self.publish_avail(self._avTopics[t], avail)

    def publish_state_topics(self):
        """ publish all state topics """
        for t in self._stTopics:
            val = self.SensorConfigs[t]["device_class"]
            self.publish_state(self._stTopics[t], encode_json(
                {f"{val}": self.SensorValues[t]}))

    def on_message(self, _client, _userdata, message):
        logging.debug(
            f" Received message  {str(message.payload) } on topic {message.topic} with QoS {str(message.qos)}")
        payload = str(message.payload.decode("utf-8"))
        logging.warning(f"Ignoring message topic {message.topic}:{payload}")

    def on_disconnect(self, _client, _userdata, rc=0):
        """
        on_disconnect by external event
        """
        if rc != 0 and not self._disconnectRQ:
            logging.error("MQTT broker was disconnected: " + str(rc))
            if 16==rc:
                logging.error("by router , WIFI access point channel has changed?")
                time.sleep(30) # some time to reconnect
            elif 7==rc:
                logging.error("broker down ?")
                time.sleep(30) # some time to reconnect
            else:
                self.loop_stop()
                logging.info(f"{self._client_id} MQTT exit (-1)!")
                exit (-1)
        else:
            logging.debug("client disconnected: " + str(rc))
            self.loop_stop()

    def client_down(self):
        """
        clean up everything when keyboard CTRL-C or daemon kill request occurs
        """
        logging.info(f"MQTT client {self._client_id} down")
        self._disconnectRQ=True
        self.publish_avail_topics(avail=False)
        self.publish(self._ONLINE_STATE, False, RETAIN)
        self.disconnect()
        self.loop_stop()

    def publish_avail(self, topic, avail=True):
        """ publish available topic """
        payload = "offline"
        if avail:
            payload = "online"

        self.publish(topic, payload, RETAIN)
        logging.debug(f"publish avail:{str(topic)}:{payload}")

    def publish_state(self, topic, payload):
        """ publish state topic """
        self.publish(topic=topic, payload=payload, retain=RETAIN)
        logging.debug(f"publish state:{str(topic)}:{payload}")

    def publish_hass(self):
        """ 
        publish all homeassistant discovery topics
        """

        """
            <discovery_prefix>/<component>/[<node_id>/]<object_id>/config
            https://www.home-assistant.io/integrations/mqtt#mqtt-discovery
            https://www.home-assistant.io/integrations/switch.mqtt/#configuration-variables
            allowed components: https://github.com/home-assistant/core/blob/dev/homeassistant/const.py
            https://www.home-assistant.io/docs/configuration/customizing-devices/#device-class
            https://www.home-assistant.io/integrations/switch.mqtt/
            https://developers.home-assistant.io/docs/device_registry_index/
    
        """
        logging.debug("publishing HASS discoveries")
        for cfg in self.SensorConfigs:
            payload = encode_json(self.SensorConfigs[cfg])
            topic = self._hassTopics[cfg]
            self.publish(topic, payload=payload, retain=True)

    def startup_client(self):
        """
        Start the MQTT client
        """
        logging.info(f'Starting up MQTT Service {self._client_id}')
        mqttattempts = 0
        while mqttattempts < self.cfg.MQTTBroker.connection_retries:
            try:
                self.username_pw_set(
                    self.cfg.MQTTBroker.username,
                    self.cfg.MQTTBroker.password)
                # no client certificate needed
                if len(self.cfg.MQTTBroker.clientcertfile) and \
                   len(self.cfg.MQTTBroker.clientkeyfile):
                    self.tls_set(certfile=self.cfg.MQTTBroker.clientcertfile,
                                 keyfile=self.cfg.MQTTBroker.clientkeyfile,
                                 cert_reqs=ssl.CERT_REQUIRED)
                else:
                    # some users reported connection problems due to this call
                    # but in my environmet this is a MUST
                    self.tls_set(cert_reqs=ssl.CERT_NONE)
                # commented out due to reported connection problems when user/pw not set
                # self.tls_insecure_set(self.cfg.MQTTBroker.insecure)

                self.connect(
                    self.cfg.MQTTBroker.host,
                    self.cfg.MQTTBroker.port)
                self.loop_start()
                mqttattempts = self.cfg.MQTTBroker.connection_retries
            except BaseException as e:
                logging.error(
                    f"{str(e)}\nCould not establish MQTT Connection! Try again \
                    {str(self.cfg.MQTTBroker.connection_retries - mqttattempts)} xtimes")
                mqttattempts += 1
                if mqttattempts == self.cfg.MQTTBroker.connection_retries:
                    logging.error(
                        f"Could not connect to MQTT Broker {self.cfg.MQTTBroker.host} exit")
                    exit(-1)
                time.sleep(2)

        # main MQTT client loop
        while True:
            logging.debug(f"{self._client_id}-Loop")
            try:
                time.sleep(self.cfg.REFRESH_RATE)
                self.poll()
                self.publish_state_topics()
            except KeyboardInterrupt:  # i.e. ctrl-c
                self.client_down()
                logging.info(f"{self._client_id} MQTT Goodbye!")
                exit(0)

            except Exception as e:
                logging.error(f"{self._client_id} exception:{str(e)}")
                self.disconnect()
                self.loop_stop()
                exit(-1)
