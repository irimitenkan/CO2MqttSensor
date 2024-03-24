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
QOS = 0

""" True: MSG is stored at Broker and keeps available for new subscribes,
    False: new publish required after subscribes
"""
RETAIN = True

# hostname = socket.gethostname()
HASS_DISCOVERY_PREFIX = 'homeassistant'

HASS_TYPE_BINARY_SENSOR = "binary_sensor"
HASS_TYPE_SENSOR = "sensor"
HASS_TYPE_BUTTON = "button"

HASS_CONFIG_DEVICE = "device"
HASS_CONFIG_DEVICE_CLASS = "device_class"
HASS_CONFIG_ICON = "icon"
HASS_CONFIG_VALUE_TEMPLATE = "value_template"
HASS_CONFIG_UNIT = "unit_of_measurement"
HASS_CONFIG_STATECLASS = "state_class"

def encode_json(value) -> str:
    return json.dumps(value)


class MQTTClient (mqtt.Client):
    """ MQTT client class with HASS discovery support """

    def __init__(self, cfg, ClientID,clientTopics:dict, hassconfigs:dict, subscrTps:dict) -> None:
        super().__init__(ClientID)
        self.CLIENT_TOPICS = clientTopics
        self.HASSCONFIGS = hassconfigs
        self.SUBSCRIBE_TOPICS = subscrTps
        self.TopicValues = dict()
        self.TopicConfigs = dict()

        self.cfg = cfg
        self._disconnectRQ = False
        self._avTopics = dict()
        self._stTopics = dict()
        self._subTopics = dict()
        self._hassTopics = dict()
        self._hostname = self._getHostTopicId()

        self._baseTopic = f"{ClientID}/{self._hostname}"
        signal.signal(signal.SIGINT, self.daemon_kill)
        signal.signal(signal.SIGTERM, self.daemon_kill)
        self._ONLINE_STATE = f"{self._baseTopic}/online"
        devId=self.setupDevice()
        self.poll() # get 1st values from device
        self.setupTopics(self.CLIENT_TOPICS,self.SUBSCRIBE_TOPICS)
        self.setupHassTopics(devId)

    def setupDevice(self):
        """
        setup device specific HASS config of
        sensors, switches, buttons  etc
        to be implemented by derived class 
        """
        pass

    def poll(self):
        """
        poll data from connected device
        to be implemented by derived class 
        """
        pass

    def setupHassTopics(self, devId:dict):
        """
        setup all topics and HASS discovery configs
        """
        for tp in self.CLIENT_TOPICS:
            json_attr = f"{self._baseTopic}/{tp}"
            unique_attr = f"{self._baseTopic}/{tp}"
            name = f"{self._client_id}.{self._hostname}.{tp}"
            # generic config attributs
            config_tp = {
                "device": devId,
                "availability_topic": self._avTopics[tp],
                "json_attributes_topic": json_attr,
                "unique_id": unique_attr,
                "state_topic": self._stTopics[tp],
                "name": name
            }
            # non generic attributs
            if tp in self.HASSCONFIGS:
                config_tp.update(self.HASSCONFIGS[tp])

            self.TopicConfigs[tp] = config_tp
        self.poll()

    def setupTopics(self, topics: dict, subscribeTps:dict):
        """
        build all required sensor topics and init sensor values
        """
        # init all topic values with 0
        self.TopicValues.update( dict(zip(topics.keys(), [0] * len(topics))) )
        for tp in topics:
            cmd=None
            if tp in subscribeTps:
                cmd=subscribeTps[tp]
            self._setupTopics(tp,topics.get(tp), cmd)

    def _setupTopics(self, tp:str , deviceclass:str, subcmd=None):
        self._avTopics[tp] = f"{self._baseTopic}/{tp}/available"
        self._stTopics[tp] = f"{self._baseTopic}/{tp}"
        self._hassTopics[tp] = f"{HASS_DISCOVERY_PREFIX}/{deviceclass}/{self._baseTopic}/{tp}/config"
        if subcmd:
            self._subTopics[tp] = f"{self._baseTopic}/{tp}/{subcmd}"

    def _getHostTopicId(self):
        return socket.gethostname()

    def daemon_kill(self, *_args):
        self.client_down()
        logging.info(f"{self._client_id} MQTT daemon Goodbye!")
        exit(0)

    def on_connect(self, _client, _userdata, _flags, rc):
        """
        on_connect when MQTT CleanSession=False (default) conn_ack will be send from broker
        """
        logging.debug(f"on_connect(): {conn_ack(rc)}")
        if 0 == rc:
            self.publish(topic=self._ONLINE_STATE, payload=True, qos=0, retain=RETAIN)
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
            val = self.TopicConfigs[t]["device_class"]
            self.publish_state(self._stTopics[t], encode_json(
                {f"{val}": self.TopicValues[t]}))

    def on_message(self, _client, _userdata, message):
        logging.debug(
            f" Received message  {str(message.payload) } on topic {message.topic} with QoS {str(message.qos)}")
        payload = str(message.payload.decode("utf-8"))
        logging.warning(f"Ignoring message topic {message.topic}:{payload}")

    def on_disconnect(self, _client, _userdata, rc=0):
        """
        on_disconnect by external event
        """
        if rc > 0 and not self._disconnectRQ:
            logging.error("MQTT broker was disconnected: " + str(rc))
            match rc:
                case 16:
                    logging.error("by router , WIFI access point channel has changed?")
                    time.sleep(30) # some time to reconnect
                case 7:
                    logging.error("broker down ?")
                    time.sleep(30) # some time to reconnect
                case 5:
                    logging.error ("not authorised")
                    self._disconnectRQ = True
                case _:
                    logging.error ("unknown reason")
                    self.loop_stop()
                    self._disconnectRQ = True
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
        self.publish(topic=topic, payload=payload, qos=0, retain=RETAIN)
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
        for cfg in self.TopicConfigs:
            payload = encode_json(self.TopicConfigs[cfg])
            topic = self._hassTopics[cfg]
            logging.debug(f"publish hass:{str(topic)}:{payload}")
            self.publish(topic, payload=payload, retain=True)

    def startup_client(self):
        """
        Start the MQTT client
        """
        logging.info(f'Starting up MQTT Service {self._client_id}')
        try:
            self.username_pw_set(
                self.cfg.MQTTBroker.username,
                self.cfg.MQTTBroker.password)
            # client certificate needed ?
            if len(self.cfg.MQTTBroker.clientcertfile) and \
               len(self.cfg.MQTTBroker.clientkeyfile):
                self.tls_set(certfile=self.cfg.MQTTBroker.clientcertfile,
                             keyfile=self.cfg.MQTTBroker.clientkeyfile,
                             cert_reqs=ssl.CERT_REQUIRED)
            res=self.connect(self.cfg.MQTTBroker.host,self.cfg.MQTTBroker.port)
            logging.debug(f"MQTT host connection result: {res}")
            if res>0:
                match res:
                    case 1: msg = "incorrect protocol version"
                    case 2: msg = "invalid client identifier"
                    case 3: msg = "server not available"
                    case 4: msg = "wrong username or password"
                    case 5: msg = "not authorised"
                    case _:msg = "unknown reason"
                logging.error(f"Broker connection failed due to {msg} and exit() ")
                exit (-1)
            self.loop_start()
            time.sleep(3)
            if self._disconnectRQ: #due to on_connect with error
                #logging.info(f"{self._client_id} MQTT Goodbye!")
                exit(-2)
        except BaseException as e:
            logging.error(
                    f"{str(e)}:could not connect to MQTT Broker {self.cfg.MQTTBroker.host} exit ()")
            exit(-1)

        # main MQTT client loop
        while True:
            logging.debug(f"{self._client_id}-Loop")
            try:
                time.sleep(self.cfg.REFRESH_RATE)
                if self._disconnectRQ:
                    logging.info(f"{self._client_id} MQTT Goodbye!")
                    exit(0)
                else:
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

