'''
Created on 19.11.2023

@author: irimi
'''
import hid
import logging
from os import urandom

TIMEOUT_MS = 5000
LOOP_ERROR = 15

# CO2 sensor items
eHum1 = 0x41
eTemp = 0x42
eHum2 = 0x44
eCO2 = 0x50
eCO2_2 = 0x71  # on my mini device
eUnkown1 = 0x6d
eUnkown2 = 0x6e

def listAllDevices():
    for device_dict in hid.enumerate():
        keys = list(device_dict.keys())
        keys.sort()
        keys.remove("usage_page")
        keys.remove("release_number")
        keys.remove("serial_number")
        keys.remove("interface_number")
        for key in keys:
            val = device_dict[key]
            if key.endswith("_id"):
                val = hex(val)
            print("%s : %s" % (key, val))
        print()


def lookforDevice(vendor_id, product_id):
    for device in hid.enumerate():
        if vendor_id == device["vendor_id"] and \
           product_id == device["product_id"]:
            return True

    return False


def to16bit(val):
    return (val[0] << 8) | val[1]

def getRandom(num = 8):
    return list(urandom(num))

def decrypt(data,key):
    """
    https://github.com/JsBergbau/TFACO2AirCO2ntrol_CO2Meter/blob/main/co2monitor.py
    """
    cstate = [0x48,  0x74,  0x65,  0x6D,  0x70,  0x39,  0x39,  0x65]

    shuffle = [2, 4, 0, 7, 1, 6, 5, 3]

    phase1 = [0] * 8
    for i, o in enumerate(shuffle):
        phase1[o] = data[i]

    phase2 = [0] * 8
    for i in range(8):
        phase2[i] = phase1[i] ^ key[i]

    phase3 = [0] * 8
    for i in range(8):
        phase3[i] = ( (phase2[i] >> 3) | (phase2[ (i-1+8)%8 ] << 5) ) & 0xff

    ctmp = [0] * 8
    for i in range(8):
        ctmp[i] = ( (cstate[i] >> 4) | (cstate[i]<<4) ) & 0xff

    out = [0] * 8
    for i in range(8):
        out[i] = (0x100 + phase3[i] - ctmp[i]) & 0xff

    return out

class CO2Device(object):
    """
    CO2 Device - see details at

    http://co2meters.com/Documentation/AppNotes/AN146-RAD-0401-serial-communication.pdf
    https://hackaday.io/project/5301-reverse-engineering-a-low-cost-usb-co-monitor/log/17909-all-your-base-are-belong-to-us

    """

    def __init__(self):
        self._dev = None
        self.key=getRandom(8)

    def hasNoHumiditySens(self, HW):
        return HW == "AIRCO2NTROL_MINI"

    def close(self):
        self._dev.close()

    def open(self, vendor, product):
        if lookforDevice(vendor, product):
            try:
                logging.debug(
                    f"try to open vendor {hex(vendor)} - product {hex(product)}")
                self._dev = hid.device()
                self._dev.open(vendor, product)
                man = self._dev.get_manufacturer_string()
                prod = self._dev.get_product_string()
                logging.debug(
                    f"CO2 devices opened: Manufacturer = {man} , Product = {prod}")
                ret=self._dev.send_feature_report([0x00] + self.key)
                logging.debug(f"enter output mode - send_feature_report: {ret}")
                return (len(self.key) +1 == ret)

            except IOError as ex:
                logging.error(ex)
                logging.error(
                    f"device available but access has failed: vendor {vendor} - product {product}")
                logging.error(
                    "Please check udev rules / access rights and/or group assigment, e.g.")
                logging.error(
                    "KERNEL==\"hidraw*\", ATTRS{idVendor}==\"04d9\", ATTRS{idProduct}==\"a052\", GROUP=\"input\", MODE=\"0660\"")
                logging.error(
                    "KERNEL==\"hidraw*\", ATTRS{idVendor}==\"04d9\", ATTRS{idProduct}==\"a052\", GROUP=\"plugdev\", MODE=\"0660\"")
                return False

        else:
            logging.error(
                f"device not available: vendor {hex(vendor)} - product {hex(product)}")
            for device in hid.enumerate():
                if vendor == device["vendor_id"]:
                    man = device["manufacturer_string"]
                    pid = device["product_id"]
                    pstr = device["product_string"]
                    logging.error(f"Same vendor {hex(vendor)}={man} found")
                    logging.error(
                        f"but different product id {hex(pid)}:{pstr}")
                    break

    def _read_(self):
        if self._dev:
            try:
                raw = self._dev.read(8, TIMEOUT_MS)

                if raw[4] == 0x0d and (sum(raw[:3]) & 0xff) == raw[3]:
                    data = raw
                else:
                    logging.debug("decrypting")
                    data = decrypt(raw,self.key)

            except IOError as ex:
                logging.error(ex)
                man = self._dev.get_manufacturer_string()
                prod = self._dev.get_product_string()
                logging.error(
                    f"IO Error CO2 device: Manufacturer = {man} , Product = {prod}")
                return list()
            return data

    def receive(self, sensorValues: dict()) -> bool:
        bCO2 = True
        bTemp = True
        if "Humidity" in sensorValues:
            bHum = True
        else:
            bHum = False  # not availbale hence do not wait for
        logging.debug(f"----> waiting for {str(sensorValues.keys())} values froom device")
        loop=0
        while (bHum or bCO2 or bTemp):  # wait since value was not received
            loop+=1
            if loop>=LOOP_ERROR:
                logging.error("unexpected values from device, missing CO2/T/H value items")
                return False

            rec = self._read_()
            if len(rec):
                item = rec[0]
                val = to16bit(rec[1:3])

                if eCO2 == item:
                    logging.debug(f"CO2 = {val} ppm")
                    sensorValues["CO2"] = f"{val}"
                    bCO2 = False
                elif eTemp == item:
                    logging.debug(f"Temperature = {val / 16.0 - 273.15:.2f} °C")
                    sensorValues["Temperature"] = f"{val / 16.0 - 273.15:.2f}"
                    bTemp = False
                    # f = t * 9 / 5 + 32
                elif bHum and (eHum1 == item or eHum2 == item):
                    logging.debug(f"Humidity = {val/100:2.2f} %")
                    sensorValues["Humidity"] = f"{val/100 :2.2f}"
                    bHum = False
                else:
                    logging.debug(
                        f"{loop}:ignoring sensor item {hex(item)}={val} (value)")
            else:
                return False
        logging.debug("<--- received values from device")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    dev = CO2Device()
    if dev.open(0x04d9, 0xa052):
        dt = dev._read_()
        print(dt)
        dev.close()
        if len(dt)>0:
            print("device test passed")
        else:
            print("device test failed:device access but no data received-")
            
    else:
        print("device access failed")
        listAllDevices()
