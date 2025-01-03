'''
Created on 17.11.2023

@author: irimi
'''

import logging, os
import MQTTClient as hass
from config import Config
from co2device import CO2Device

MQTT_CLIENT_ID = 'co2sensor'

""" Logging level: INFO, DEBUG, ERROR, WARN  """
LOG_LEVEL = {
    "INFO": logging.INFO,
    "ERROR": logging.ERROR,
    "WARN": logging.WARN,
    "DEBUG": logging.DEBUG
}

class Co2SensorClient (hass.MQTTClient):
    """  CO2 Sensor MQTT client class """

    def __init__(self, cfg, version):
        self.version = version
        super().__init__(cfg, MQTT_CLIENT_ID)

    def setupClientTopics(self)->dict:
        """
        get a dict() which defines the required client topic
        based on HASS types
        to be implemented by derived class
        """
        clientTopics = {'CO2': hass.HASS_COMPONENT_SENSOR,
                              'Temperature': hass.HASS_COMPONENT_SENSOR,
                              'Humidity': hass.HASS_COMPONENT_SENSOR}
        return clientTopics

    def setupHassDiscoveryConfigs(self) -> dict:
        """
        get a dict() which defines the required config topics
        based on HASS
        to be implemented by derived class
        """
        hassconfigs = {'CO2': {hass.HASS_CONFIG_ICON:"mdi:molecule-co2",
                               hass.HASS_CONFIG_DEVICE_CLASS : "carbon_dioxide",
                               hass.HASS_CONFIG_VALUE_TEMPLATE :"{{ value_json.carbon_dioxide  }}",
                               hass.HASS_CONFIG_UNIT : "ppm",
                               hass.HASS_CONFIG_STATECLASS : "measurement"
                               },
                       'Temperature': {hass.HASS_CONFIG_ICON:"mdi:temperature-celsius",
                               hass.HASS_CONFIG_DEVICE_CLASS : "temperature",
                               hass.HASS_CONFIG_VALUE_TEMPLATE :"{{ value_json.temperature  }}",
                               hass.HASS_CONFIG_UNIT : "°C",
                               hass.HASS_CONFIG_STATECLASS : "measurement"
                               },
                       'Humidity': {hass.HASS_CONFIG_ICON:"mdi:water-percent",
                               hass.HASS_CONFIG_DEVICE_CLASS : "humidity",
                               hass.HASS_CONFIG_VALUE_TEMPLATE :"{{ value_json.humidity  }}",
                               hass.HASS_CONFIG_UNIT : "%",
                               hass.HASS_CONFIG_STATECLASS : "measurement"
                               }
                        }
        return hassconfigs

    def setupDevice(self):
        """
        setup device specific sensors
        """
        self.device = CO2Device()
        if not self.device.open(int(self.cfg.VENDOR, 16), int(self.cfg.PRODUCT, 16)):
            logging.error(f"access failure: vendor: {self.cfg.VENDOR} product: {self.cfg.PRODUCT}")
            logging.error("program exit(-1)")
            exit(-1)
        if self.device.hasNoHumiditySens(self.cfg.HW):
            logging.debug("Humidity sensor not supported by and removed")
            del self.CLIENT_TOPICS["Humidity"]
            del self.HASSCONFIGS["Humidity"]

        logging.debug(
            f"SW activated sensors due to HW={self.cfg.HW} : {str(self.CLIENT_TOPICS.keys())}")

        mqtt_device = {
            "identifiers": [f"{MQTT_CLIENT_ID}_{self._hostname}"],
            "manufacturer": "TFA Dostmann",
            "model": self.cfg.HW,
            "sw_version": self.version,
            "name": f"{MQTT_CLIENT_ID}.{self._hostname}"
        }
        return mqtt_device

    def poll(self):
        """
        poll data from device
        """
        return (self.device.receive(self.TopicValues))

    def client_down(self):
        super().client_down()
        self.device.close()

def startClient(cfgfile: str, version: str):
    """
    generator help function to create MQTT client instance  & start it
    """
    cfg = Config.load_json(cfgfile)
    logging.basicConfig(level=LOG_LEVEL[cfg.LogLevel],
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%H:%M:%S')
    client = Co2SensorClient(cfg, version)
    if "posix" in os.name and os.geteuid() == 0:
        logging.warning(f"It is not recommended to execute CO2MQTTSensor as root")

    client.startup_client()
