import os
import itertools
import socket
import time
from adb import Adb
from not_found_handler import NotFoundHandler
from utils import next_local_port
from constants import DEVICE_PORT
from json_rpc_method import JsonRPCMethod
from json_rpc_error import JsonRPCError
from json_rpc_client import JsonRPCClient

try:
    import urllib2
except ImportError:
    import urllib.request as urllib2
try:
    from httplib import HTTPException
except:
    from http.client import HTTPException
try:
    if os.name == 'nt':
        import urllib3
except:  # to fix python setup error on Windows.
    pass


class AutomatorServer(object):

    """start and quit rpc server on device.
    """
    __jar_files = {
        "bundle.jar": "libs/bundle.jar",
        "uiautomator-stub.jar": "libs/uiautomator-stub.jar"
    }

    __apk_files = ["libs/app-uiautomator.apk", "libs/app-uiautomator-test.apk"]

    __sdk = 0

    handlers = NotFoundHandler()  # handler UI Not Found exception

    def __init__(self, serial=None, local_port=None, device_port=None, adb_server_host=None, adb_server_port=None):
        self.uiautomator_process = None
        self.adb = Adb(serial=serial, adb_server_host=adb_server_host, adb_server_port=adb_server_port)
        self.device_port = int(device_port) if device_port else DEVICE_PORT
        if local_port:
            self.local_port = local_port
        else:
            try:  # first we will try to use the local port already adb forwarded
                for s, lp, rp in self.adb.forward_list():
                    if s == self.adb.device_serial() and rp == 'tcp:%d' % self.device_port:
                        self.local_port = int(lp[4:])
                        break
                else:
                    self.local_port = next_local_port(adb_server_host)
            except:
                self.local_port = next_local_port(adb_server_host)

    def push(self):
        base_dir = os.path.dirname(__file__)
        for jar, url in self.__jar_files.items():
            filename = os.path.join(base_dir, url)
            self.adb.cmd("push", filename, "/data/local/tmp/").wait()
        return list(self.__jar_files.keys())

    def install(self):
        base_dir = os.path.dirname(__file__)
        for apk in self.__apk_files:
            self.adb.cmd("install", "-r -t", os.path.join(base_dir, apk)).wait()

    @property
    def jsonrpc(self):
        return self.jsonrpc_wrap(timeout=int(os.environ.get("jsonrpc_timeout", 90)))

    def jsonrpc_wrap(self, timeout):
        server = self
        ERROR_CODE_BASE = -32000

        def _JsonRPCMethod(url, method, timeout, restart=True):
            _method_obj = JsonRPCMethod(url, method, timeout)

            def wrapper(*args, **kwargs):
                URLError = urllib3.exceptions.HTTPError if os.name == "nt" else urllib2.URLError
                try:
                    return _method_obj(*args, **kwargs)
                except (URLError, socket.error, HTTPException) as e:
                    if restart:
                        server.stop()
                        server.start(timeout=30)
                        return _JsonRPCMethod(url, method, timeout, False)(*args, **kwargs)
                    else:
                        raise
                except JsonRPCError as e:
                    if e.code >= ERROR_CODE_BASE - 1:
                        server.stop()
                        server.start()
                        return _method_obj(*args, **kwargs)
                    elif e.code == ERROR_CODE_BASE - 2 and self.handlers['on']:  # Not Found
                        try:
                            self.handlers['on'] = False
                            # any handler returns True will break the left handlers
                            any(handler(self.handlers.get('device', None)) for handler in self.handlers['handlers'])
                        finally:
                            self.handlers['on'] = True
                        return _method_obj(*args, **kwargs)
                    raise
            return wrapper

        return JsonRPCClient(self.rpc_uri,
                             timeout=timeout,
                             method_class=_JsonRPCMethod)

    def __jsonrpc(self):
        return JsonRPCClient(self.rpc_uri, timeout=int(os.environ.get("JSONRPC_TIMEOUT", 90)))

    def sdk_version(self):
        '''sdk version of connected device.'''
        if self.__sdk == 0:
            try:
                self.__sdk = int(self.adb.cmd("shell", "getprop", "ro.build.version.sdk").communicate()[0].decode("utf-8").strip())
            except:
                pass
        return self.__sdk

    def start(self, timeout=5):
        if self.sdk_version() < 18:
            files = self.push()
            cmd = list(itertools.chain(
                ["shell", "uiautomator", "runtest"],
                files,
                ["-c", "com.github.uiautomatorstub.Stub"]
            ))
        else:
            self.install()
            cmd = ["shell", "am", "instrument", "-w",
                   "com.github.uiautomator.test/android.support.test.runner.AndroidJUnitRunner"]

        self.uiautomator_process = self.adb.cmd(*cmd)
        self.adb.forward(self.local_port, self.device_port)

        while not self.alive and timeout > 0:
            time.sleep(0.1)
            timeout -= 0.1
        if not self.alive:
            raise IOError("RPC server not started!")

    def ping(self):
        try:
            return self.__jsonrpc().ping()
        except:
            return None

    @property
    def alive(self):
        '''Check if the rpc server is alive.'''
        return self.ping() == "pong"

    def stop(self):
        '''Stop the rpc server.'''
        if self.uiautomator_process and self.uiautomator_process.poll() is None:
            res = None
            try:
                res = urllib2.urlopen(self.stop_uri)
                self.uiautomator_process.wait()
            except:
                self.uiautomator_process.kill()
            finally:
                if res is not None:
                    res.close()
                self.uiautomator_process = None
        try:
            out = self.adb.cmd("shell", "ps", "-C", "uiautomator").communicate()[0].decode("utf-8").strip().splitlines()
            if out:
                index = out[0].split().index("PID")
                for line in out[1:]:
                    if len(line.split()) > index:
                        self.adb.cmd("shell", "kill", "-9", line.split()[index]).wait()
        except:
            pass

    @property
    def stop_uri(self):
        return "http://%s:%d/stop" % (self.adb.adb_server_host, self.local_port)

    @property
    def rpc_uri(self):
        return "http://%s:%d/jsonrpc/0" % (self.adb.adb_server_host, self.local_port)

    @property
    def screenshot_uri(self):
        return "http://%s:%d/screenshot/0" % (self.adb.adb_server_host, self.local_port)

    def screenshot(self, filename=None, scale=1.0, quality=100):
        if self.sdk_version() >= 18:
            try:
                req = urllib2.Request("%s?scale=%f&quality=%f" % (self.screenshot_uri, scale, quality))
                result = urllib2.urlopen(req, timeout=30)
                if filename:
                    with open(filename, 'wb') as f:
                        f.write(result.read())
                        return filename
                else:
                    return result.read()
            except:
                pass
        return None
