#!/usr/bin/python3
# encoding: utf-8
'''
CO2MqttSensor

@author:     irimi@gmx.de

@copyright:  irimi@gmx.de - All rights reserved.

@license:    GNU GENERAL PUBLIC LICENSE Version 3

@contact:    irimi@gmx.de

'''

import sys
import os

from optparse import OptionParser
from co2sensorclient import startClient

__all__ = []
__version__ = "0.2.3"
__updated__ = '2024-07-21'
__author__ = "irimi@gmx.de"


def main(argv=None):
    '''Command line options.'''

    program_name = os.path.basename(sys.argv[0])
    program_version = f"v{__version__}"
    program_version_string = f"{program_name} {program_version} {__updated__}"
    program_license = "Copyright 2023-2024 irimi@gmx.de, published under GPL-3.0"

    if argv is None:
        argv = sys.argv[1:]
    # setup option parser
    parser = OptionParser(
        version=program_version_string,
        epilog="your CO2Sensor MQTT client for Home Assistant",
        description=program_license)

    parser.add_option(
        "-c",
        "--cfg",
        dest="cfgfile",
        help="set config file [default: %default]",
        metavar="FILE")

    parser.set_defaults(cfgfile="./config.json")
    (opts, _args) = parser.parse_args(argv)

    if opts.cfgfile:
        print("cfgfile = %s" % opts.cfgfile)

    startClient(opts.cfgfile, __version__)


if __name__ == "__main__":
    sys.exit(main())
