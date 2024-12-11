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

HASS_COMPONENT_BINARY_SENSOR = "binary_sensor"
HASS_COMPONENT_SENSOR = "sensor"
HASS_COMPONENT_BUTTON = "button"
HASS_COMPONENT_SWITCH = "switch"
HASS_COMPONENT_NUMBER = "number"

HASS_CONFIG_DEVICE = "device"
HASS_CONFIG_DEVICE_CLASS = "device_class"
HASS_CONFIG_ICON = "icon"
HASS_CONFIG_VALUE_TEMPLATE = "value_template"
HASS_CONFIG_UNIT = "unit_of_measurement"
HASS_CONFIG_STATECLASS = "state_class"
HASS_CONFIG_COMMAND = "command_topic"
HASS_CONFIG_PAYLOAD_ON = "payload_on"
HASS_CONFIG_PAYLOAD_OFF = "payload_off"

DEBOUNCE_THRESHOLD = 2

def encode_json(value) -> str:
    return json.dumps(value)

def toStr(bstr:bytes)->str:
    return str(bstr, encoding='utf-8')

class MQTTClient (mqtt.Client):
    """ MQTT client class with HASS discovery support """

    def __init__(self, cfg, ClientID) -> None:
        super().__init__(ClientID)

        self.cfg = cfg
        self._disconnectRQ = False
        self._disconnectCnt = 0
        self._hostname = self._getHostTopicId()
        self.baseTopic = f"{ClientID}/{self._hostname}"
        signal.signal(signal.SIGINT, self.daemon_kill)
        signal.signal(signal.SIGTERM, self.daemon_kill)
        self._ONLINE_STATE = f"{self.baseTopic}/online"

        self.CLIENT_TOPICS = self.setupClientTopics()
        self.HASSCONFIGS = self.setupHassDiscoveryConfigs()
        self.SUBSCRIBE_TOPICS = self.setupSubscribeTopics()
        if len(self.CLIENT_TOPICS) != len(self.HASSCONFIGS):
            logging.warning("check your Topic setup: different sizes !")

        self.TopicValues = dict()
        self.TopicConfigs = dict()

        self._avTopics = dict()
        self._stTopics = dict()
        self._subTopics = dict()
        self._hassTopics = dict()

        devId=self.setupDevice()
        if self.poll(): # get 1st values from device
            self._setupTopics(self.CLIENT_TOPICS,self.SUBSCRIBE_TOPICS)
            self._setupHassTopics(devId)

    def setupDevice(self):
        """
        setup device used for client communication
        to be implemented by derived class
        """
        pass

    def setupClientTopics(self) -> dict:
        """
        get a dict() which defines the required client topics
        based on HASS types
        to be implemented by derived class
        """
        return dict() #default empty dict

    def setupHassDiscoveryConfigs(self) -> dict:
        """
        get a dict() which defines the required config topic
        based on HASS
        to be implemented by derived class
        """
        return dict() #default empty dict

    def setupSubscribeTopics(self) -> dict:
        """
        get a dict() which defines the required subscribe topics
        to be implemented by derived class
        """
        return dict() #default empty dict

    def poll(self):
        """
        poll data from connected device
        to be implemented by derived class 
        """
        pass

    def _setupHassTopics(self, devId:dict):
        """
        setup all topics and HASS discovery configs
        """
        for tp in self.CLIENT_TOPICS:
            json_attr = f"{self.baseTopic}/{tp}"
            unique_attr = f"{self.baseTopic}/{tp}"
            name = f"{toStr(self._client_id)}.{self._hostname}.{tp}"
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

    def _setupTopics(self, topics: dict, subscribeTps:dict):
        """
        build all required sensor topics and init sensor values
        """
        # init all topic values with 0
        self.TopicValues.update( dict(zip(topics.keys(), [0] * len(topics))) )
        for tp in topics:
            cmd=None
            if tp in subscribeTps:
                cmd=subscribeTps[tp]
            self._setupTopic(tp,topics.get(tp), cmd)

    def _setupTopic(self, tp:str , deviceclass:str, subcmd=None):
        self._avTopics[tp] = f"{self.baseTopic}/{tp}/available"
        self._stTopics[tp] = f"{self.baseTopic}/{tp}/state"
        # hassTopic pattern :<discovery_prefix>/<component>/[<node_id>/]<object_id>/config
        self._hassTopics[tp] = f"{HASS_DISCOVERY_PREFIX}/{deviceclass}/{self._hostname}/{tp}/config"
        if subcmd:
            self._subTopics[tp] = f"{self.baseTopic}/{tp}/{subcmd}"

    def _getHostTopicId(self):
        """
        defines the node_id in hass discovery topic
        """
        return socket.gethostname()

    def daemon_kill(self, *_args):
        """
        called by ctrl-c event
        """
        self.client_down()
        logging.info(f"{toStr(self._client_id)} MQTT daemon Goodbye!")
        exit(0)

    def on_connect(self, _client, _userdata, _flags, rc):
        """
        on_connect when MQTT CleanSession=False (default) conn_ack will be send from broker
        """
        logging.debug(f"on_connect(): {conn_ack(rc)}")
        if 0 == rc:
            self.publish_hass()
            time.sleep(1)
            self.publish_avail_topics()
            time.sleep(1)
            self.publish(topic=self._ONLINE_STATE, payload=True, qos=0, retain=RETAIN)
            self.publish_state_topics()

    def publish_avail_topics(self, avail=True):
        """ publish all available topics """
        for t in self._avTopics:
            self.publish_avail(self._avTopics[t], avail)

    def publish_state_topics(self):
        """ publish all state topics """
        for t in self._stTopics:
            val = self.HASSCONFIGS[t]["device_class"]
            if HASS_COMPONENT_SWITCH == val:
                self.publish_state(self._stTopics[t],self.TopicValues[t])
            else:
                self.publish_state(self._stTopics[t], encode_json(
                    {f"{val}": self.TopicValues[t]}))

    def on_message(self, _client, _userdata, message):
        """
        on_message event by broker
        """
        logging.debug(
            f" Received message  {str(message.payload) } on topic {message.topic} with QoS {str(message.qos)}")
        payload = str(message.payload.decode("utf-8"))
        logging.warning(f"Ignoring message topic {message.topic}:{payload}")

    def on_disconnect(self, _client, _userdata, rc=0):
        """
        on_disconnect by external event
        """
        if rc > 0 and not self._disconnectRQ:
            logging.error(f"MQTT broker was disconnected: errorcode={rc} ")
            match rc:
                case 16:
                    logging.error("- by router , WIFI access point channel has changed?")
                    self._disconnectCnt+=1
                case 7:
                    logging.error("- broker down ?")
                    self._disconnectCnt+=1
                case 5:
                    logging.error ("- not authorised")
                    self._disconnectRQ = True
                case 2:
                    logging.error ("- client protocoll error (wrong broker port?)")
                    self._disconnectRQ = True
                case _:
                    logging.error ("unknown reason")
                    self.loop_stop()
                    self._disconnectRQ = True
            if self._disconnectCnt>=DEBOUNCE_THRESHOLD:
                    logging.info (f"disconnect debounce cnt = {self._disconnectCnt} ")
                    logging.error ("connction broken - exit")
                    self.loop_stop()
                    self._disconnectRQ = True
        else:
            logging.debug("client disconnected: " + str(rc))
            self.loop_stop()

    def client_down(self):
        """
        clean up everything when keyboard CTRL-C or daemon kill request occurs
        """
        logging.info(f"MQTT client {toStr(self._client_id)} down")
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
        logging.info(f'Starting up MQTT Service {toStr(self._client_id)}')
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
                    f"{str(e)}: connection to MQTT Broker {self.cfg.MQTTBroker.host} has failed & exit ()")
            exit(-3)

        # main MQTT client loop
        while True:
            logging.debug(f"{toStr(self._client_id)}-Loop")
            try:
                time.sleep(self.cfg.REFRESH_RATE)
                if self._disconnectRQ:
                    logging.info(f"{toStr(self._client_id)} MQTT Goodbye!")
                    exit(0)
                else:
                    if self.poll():
                        self.publish_state_topics()
                    else:
                        logging.error(f"{toStr(self._client_id)}: polling has failed")
                        self.client_down()
                        exit(-2)
            except KeyboardInterrupt:  # i.e. ctrl-c
                self.client_down()
                logging.info(f"{toStr(self._client_id)} MQTT Goodbye!")
                exit(0)

            except Exception as e:
                logging.error(f"{toStr(self._client_id)} exception:{str(e)}")
                self.disconnect()
                self.loop_stop()
                exit(-1)

