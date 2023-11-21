'''
Created on 17.11.2023

@author: irimi
'''

import logging
from MQTTClient import MQTTClient
from config import Config
from co2device import CO2Device

MQTT_CLIENT_ID = 'CO2Sensor'

""" Logging level: INFO, DEBUG, ERROR, WARN  """
LOG_LEVEL = {
    "INFO": logging.INFO,
    "ERROR": logging.ERROR,
    "WARN": logging.WARN,
    "DEBUG": logging.DEBUG
}


class Co2SensorClient (MQTTClient):
    """  CO2 Sensor MQTT client class """

    def __init__(self, cfg, version):
        self.SENSOR_TOPICS = ["CO2", "Temperature", "Humidity"]
        self.device = CO2Device()
        self.errorcount=0
        self.version = version
        if self.device.hasNoHumiditySens(cfg.HW):
            logging.debug("Humidity sensor not supported by and removed")
            self.SENSOR_TOPICS.remove("Humidity")

        logging.debug(
            f"SW activated sensors due to HW={cfg.HW} : {str(self.SENSOR_TOPICS)}")

        if self.device.open(int(cfg.VENDOR, 16), int(cfg.PRODUCT, 16)):
            super().__init__(cfg, MQTT_CLIENT_ID)
        else:
            logging.error("program exit(-1)")
            exit(-1)

    def setupDevices(self):
        """
        setup device specific sensors
        """
        self._setupSensorTopics(self.SENSOR_TOPICS)

        sensor_device = {
            "identifiers": [f"{MQTT_CLIENT_ID}_{self._hostname}"],
            "manufacturer": "TFA Dostmann",
            "model": self.cfg.HW,
            "sw_version": self.version,
            "name": f"{MQTT_CLIENT_ID}.{self._hostname}"
        }

        for sensor in self.SENSOR_TOPICS:
            json_attr = f"{self._baseTopic}/{sensor}"
            unique_attr = f"{self._baseTopic}/{sensor}"
            name = f"{MQTT_CLIENT_ID}.{self._hostname}{sensor}"
            if sensor == "CO2":
                config_sens = {
                    "device": sensor_device,
                    "availability_topic": self._avTopics[sensor],
                    "device_class": "carbon_dioxide",
                    "icon": "mdi:molecule-co2",
                    "json_attributes_topic": json_attr,
                    "state_class": "measurement",
                    "unit_of_measurement": "ppm",
                    "unique_id": unique_attr,
                    "state_topic": self._stTopics[sensor],
                    "name": name,
                    "value_template": "{{ value_json.carbon_dioxide }}"
                }
            elif sensor == "Temperature":
                config_sens = {
                    "device": sensor_device,
                    "availability_topic": self._avTopics[sensor],
                    "device_class": "temperature",
                    "icon": "mdi:temperature-celsius",
                    "json_attributes_topic": json_attr,
                    "state_class": "measurement",
                    "unit_of_measurement": "°C",
                    "unique_id": unique_attr,
                    "state_topic": self._stTopics[sensor],
                    "name": name,
                    "value_template": "{{ value_json.temperature }}"
                }
            elif sensor == "Humidity":
                config_sens = {
                    "device": sensor_device,
                    "availability_topic": self._avTopics[sensor],
                    "device_class": "humidity",
                    "icon": "mdi:water-percent",
                    "json_attributes_topic": json_attr,
                    "state_class": "measurement",
                    "unit_of_measurement": "%",
                    "unique_id": unique_attr,
                    "state_topic": self._stTopics[sensor],
                    "name": name,
                    "value_template": "{{ value_json.humidity }}"
                }
            else:
                logging.warning("No sensor config for {sensor} defined")
                continue

            self.SensorConfigs[sensor] = config_sens

        self.poll()

    def poll(self):
        """
        poll data from device
        """
        self.device.receive(self.SensorValues)
        self.publish_state_topics()
        # if self.device.receive(self.SensorValues):
        #     self.publish_state_topics()
        # else:
        #     self.errorcount+=1
        #     if self.errorcount>1:
        #         self.client_down()

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
    client.startup_client()
