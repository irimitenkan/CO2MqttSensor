'''
Created on 17.11.2023

@author: irimi
'''

import json

class Dict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

# found at
# https://stackoverflow.com/questions/19078170/python-how-would-you-save-a-simple-settings-config-file
class Config(object):
    @staticmethod
    def __load__(data):
        if isinstance(data, dict):
            return Config.load_dict(data)
        elif isinstance(data, list):
            return Config.load_list(data)
        else:
            return data

    @staticmethod
    def load_dict(data: dict):
        result = Dict()
        for key, value in data.items():
            result[key] = Config.__load__(value)
        return result

    @staticmethod
    def load_list(data: list):
        result = [Config.__load__(item) for item in data]
        return result

    @staticmethod
    def load_json(path: str):
        with open(path, "r") as f:
            result = Config.__load__(json.loads(f.read()))
        return result


class CheckConfig (object):

    @staticmethod
    def HasHumidity(cfg:Config) -> bool:
        if cfg.HW == "AIRCO2NTROL_MINI":
            return False
        else:
            return True
    