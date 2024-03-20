# CO2MqttSensor
[Installation](#Installation) |
[Running the MQTT client](#Running) |
[Configuration](#Configuration) |
[Adapt UDEV rules](#UDEV-rules) |
[Home Assistant Integration](#HASS-Integration)|
[MQTT Broker Topics](#MQTT-Broker)

# Overview

*CO2MqttSensor* is a MQTT client to integrate a CO2 sensor into your home automation with [Home Assistant](https://www.home-assistant.io/) discovery support.

A TFA CO2 sensor device with USB support in combination with a [Raspberry Pi Zero](https://www.raspberrypi.com/products/raspberry-pi-zero/) or [Zero 2W](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/), you'll get a cheap and easy to use CO2 sensor with WiFi network access for your home automation like [Home Assistant](https://www.home-assistant.io/).

Supported CO2 devices are:
1. [TFA CO2-Monitor-Airco2ntrol-Mini, without humidity measurement](https://www.tfa-dostmann.de/en/product/co2-monitor-airco2ntrol-mini-31-5006)

2. still untested:[TFA CO2-Monitor-Airco2ntrol-Coach, incl. humidity measurement](https://www.tfa-dostmann.de/en/product/co2-monitor-airco2ntrol-coach-31-5009)

3. Support of other available TFA devices with USB port is still unknown 

Developement is based on this [Hackaday Project ](https://hackaday.io/project/5301). There you'll find other projects derived from that Hackaday project. Some sensor's device communication documentation you'll find [here](http://co2meters.com/Documentation/AppNotes/AN146-RAD-0401-serial-communication.pdf)


# Installation

Required packages for Raspberry-Pi OS:

  ```
  sudo apt-get install -y --no-install-recommends python3-paho-mqtt python3-hid
  ```


On my Arch Linux / Manjaro system the correct package were:

  ```
  sudo pacman -S python-paho-mqtt python-hidapi
  ```

finally clone the CO2MqttSensor repository:

  ```
  git clone https://github.com/irimitenkan/CO2MqttSensor.git
  ```

## Homeassistant OS

You have to install and setup the [add-on](https://www.home-assistant.io/addons/) "[Mosquitto broker](https://www.home-assistant.io/integrations/mqtt/)".
Install *CO2MqttSensor* MQTT client on other device e.g. Rasperry Pi Zero.

# Configuration

Example config.json


  ```
  {
    "LogLevel":"INFO",
    "HW":"AIRCO2NTROL_MINI",  
    "//HW":"AIRCO2NTROL_COACH",
    "VENDOR":"0x04d9",
    "PRODUCT":"0xa052",
    "TFA_MINI_WWW_LINK":"https://www.tfa-dostmann.de/en/product/co2-monitor-airco2ntrol-mini-31-5006/",
    "TFA_COACH_WWW_LINK":"https://www.tfa-dostmann.de/en/product/co2-monitor-airco2ntrol-coach-31-5009/",

    "REFRESH_RATE":60,

      "MQTTBroker":{
      "host":"<ADDRESS OF BROKER>",
      "port": 8883,
      "username":"<USERNAME>",
      "password":"<SECRET>",
      "insecure":true,
      "connection_retries":3,
      "clientkeyfile":"",
      "clientcertfile":""
    }

}

  ```
## CFG - Option
- option REFRESH_RATE: value in [s] to poll data from device

- option loglevel:INFO | WARN | DEBUG

- option "HW":"AIRCO2NTROL_MINI" or "AIRCO2NTROL_COACH"
  (AIRCO2NTROL_COACH still untested)
- option: "VENDOR":"0x04d9",
          "PRODUCT":"0xa052",

   These are the value IDs for AIRCO2NTROL_MINI. For other TFA CO2 devices with USB port try this on you linux maschine:

  * connect sensor device with USB port and type 

  ```
  sudo dmesg 
  ```

  * you will see the vendor and product id at end of output like this:

 ```
[ 4682.882895] usb 1-1: New USB device found, idVendor=04d9, idProduct=a052, bcdDevice= 2.00
[ 4682.882921] usb 1-1: New USB device strings: Mfr=1, Product=2, SerialNumber=3
[ 4682.882936] usb 1-1: Product: USB-zyTemp
[ 4682.882949] usb 1-1: Manufacturer: Holtek
[ 4682.882962] usb 1-1: SerialNumber: 2.00
[ 4682.892497] hid-generic 0003:04D9:A052.0004: hiddev96,hidraw0: USB HID v1.10 Device [Holtek USB-zyTemp] on usb-3f980000.usb-1/input0
  ```

# UDEV-rules

Since you have not adapted your UDEV rules on your *CO2MqttSensor* host the python scripts runs only with root access.
To execute *CO2MQttSensor* without root access you must define a udev-rules to assign different access right when the CO2 sensor device is connected:

create a file `/etc/udev/rules.d/99-hidraw-permissions.rules`
and add this line:
`KERNEL=="hidraw*", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="a052", GROUP="plugdev", MODE="0660"`

on e.g.ARCH linux systems you may change the group to 
`KERNEL=="hidraw*", ATTRS{idVendor}=="04d9", ATTRS{idProduct}=="a052", GROUP="input", MODE="0660"`

then restart udev
`sudo udevadm control --reload-rules`
and finally disconnect and reconnect you CO2 device from USB port.

# Running
-to start from terminal

  ```
  cd CO2MmqttSensor
  python3 co2sensor.py
  ```
with option: -c FILE, --cfg=FILE  set config file default: ./config.json

-to stop it & started from terminal

  ```
  enter CTRL-C
  ```

-to enable at startup and start service:

  ```
  loginctl enable-linger
  systemctl --user enable --now ~/CO2MqttSensor/co2sensor.service
  ```

-to disable running service at startup and stop it:

  ```
  systemctl --user disable --now co2sensor
  ```

-to stop the service again

  ```
  systemctl --user stop co2sensor
  ```

-to start the service

  ```
  systemctl --user start co2sensor
  ```

-check the status of the service

  ```
  systemctl --user status co2sensor
  ```

-check the *CO2MqttSensor* specific service logs

  ```
  journalctl --user-unit co2sensor
  ```

# HASS-Integration
All *CO2MqttSensor* entities will be detected by Home Assistant automatically by
MQTT integration discovery function via configured MQTT broker since *CO2MqttSensor* has started and connected to broker successfully.

# MQTT-Broker

## Value topic
- `CO2Sensor/< HOSTNAME >/CO2/{"carbon_dioxide": "[value in ppm]"}`
- `CO2Sensor/< HOSTNAME >/Temperature/{"temperature": "[value in °C]"}`

Depends on used TFA sensor hardware:
- `CO2Sensor/< HOSTNAME >/Humidity/{"humidity": "[value in %]"}`

## Online status topic
- `CO2Sensor/< HOSTNAME >/CO2/available=[online|offline]`
- `CO2Sensor/< HOSTNAME >/Temperature/available=[online|offline]`

Depends on used TFA sensor hardware:
- `CO2Sensor/< HOSTNAME >/Humidity/available=[online|offline]`
