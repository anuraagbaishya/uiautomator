#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python wrapper for Android uiautomator tool."""

import os
import utils
from adb import Adb
from selector import Selector
from json_rpc_error import JsonRPCError
from json_rpc_client import JsonRPCClient
from json_rpc_method import JsonRPCMethod
from constants import DEVICE_PORT, LOCAL_PORT
from automator_server import AutomatorServer
from automator_device import device, Device, AutomatorDevice
from automator_device_object import AutomatorDeviceObject
from automator_device_uiobject import AutomatorDeviceUiObject
from automator_device_named_uiobject import AutomatorDeviceNamedUiObject

if 'localhost' not in os.environ.get('no_proxy', ''):
    os.environ['no_proxy'] = "localhost,%s" % os.environ.get('no_proxy', '')

__author__ = "Xiaocong He"
__all__ = ["device", "Device", "utils", "Selector", "JsonRPCError", "JsonRPCClient", "JsonRPCMethod", "Adb",
           "AutomatorDevice", "AutomatorDeviceObject", "AutomatorDeviceUiObject", "AutomatorDeviceNamedUiObject", "AutomatorServer"]





