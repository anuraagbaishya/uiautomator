import os
import xml.dom.minidom
from selector import Selector
from utils import param_to_property, U
from automator_server import AutomatorServer
from automator_device_object import AutomatorDeviceObject


class AutomatorDevice(object):

    '''uiautomator wrapper of android device'''

    __orientation = (  # device orientation
        (0, "natural", "n", 0),
        (1, "left", "l", 90),
        (2, "upsidedown", "u", 180),
        (3, "right", "r", 270)
    )
    __alias = {
        "width": "displayWidth",
        "height": "displayHeight"
    }

    def __init__(self, serial=None, local_port=None, adb_server_host=None, adb_server_port=None):
        self.server = AutomatorServer(
            serial=serial,
            local_port=local_port,
            adb_server_host=adb_server_host,
            adb_server_port=adb_server_port
        )

    def __call__(self, **kwargs):
        return AutomatorDeviceObject(self, Selector(**kwargs))

    def __getattr__(self, attr):
        '''alias of fields in info property.'''
        info = self.info
        if attr in info:
            return info[attr]
        elif attr in self.__alias:
            return info[self.__alias[attr]]
        else:
            raise AttributeError("%s attribute not found!" % attr)

    @property
    def info(self):
        '''Get the device info.'''
        return self.server.jsonrpc.deviceInfo()

    def click(self, x, y):
        '''click at arbitrary coordinates.'''
        return self.server.jsonrpc.click(x, y)

    def long_click(self, x, y):
        '''long click at arbitrary coordinates.'''
        return self.swipe(x, y, x + 1, y + 1)

    def swipe(self, sx, sy, ex, ey, steps=100):
        return self.server.jsonrpc.swipe(sx, sy, ex, ey, steps)

    def swipePoints(self, points, steps=100):
        ppoints = []
        for p in points:
            ppoints.append(p[0])
            ppoints.append(p[1])
        return self.server.jsonrpc.swipePoints(ppoints, steps)

    def drag(self, sx, sy, ex, ey, steps=100):
        '''Swipe from one point to another point.'''
        return self.server.jsonrpc.drag(sx, sy, ex, ey, steps)

    def dump(self, filename=None, compressed=True, pretty=True):
        '''dump device window and pull to local file.'''
        content = self.server.jsonrpc.dumpWindowHierarchy(compressed, None)
        if filename:
            with open(filename, "wb") as f:
                f.write(content.encode("utf-8"))
        if pretty and "\n " not in content:
            xml_text = xml.dom.minidom.parseString(content.encode("utf-8"))
            content = U(xml_text.toprettyxml(indent='  '))
        return content

    def screenshot(self, filename, scale=1.0, quality=100):
        '''take screenshot.'''
        result = self.server.screenshot(filename, scale, quality)
        if result:
            return result

        device_file = self.server.jsonrpc.takeScreenshot("screenshot.png",
                                                         scale, quality)
        if not device_file:
            return None
        p = self.server.adb.cmd("pull", device_file, filename)
        p.wait()
        self.server.adb.cmd("shell", "rm", device_file).wait()
        return filename if p.returncode is 0 else None

    def freeze_rotation(self, freeze=True):
        '''freeze or unfreeze the device rotation in current status.'''
        self.server.jsonrpc.freezeRotation(freeze)

    @property
    def orientation(self):
        '''
        orienting the devie to left/right or natural.
        left/l:       rotation=90 , displayRotation=1
        right/r:      rotation=270, displayRotation=3
        natural/n:    rotation=0  , displayRotation=0
        upsidedown/u: rotation=180, displayRotation=2
        '''
        return self.__orientation[self.info["displayRotation"]][1]

    @orientation.setter
    def orientation(self, value):
        '''setter of orientation property.'''
        for values in self.__orientation:
            if value in values:
                # can not set upside-down until api level 18.
                self.server.jsonrpc.setOrientation(values[1])
                break
        else:
            raise ValueError("Invalid orientation.")

    @property
    def last_traversed_text(self):
        '''get last traversed text. used in webview for highlighted text.'''
        return self.server.jsonrpc.getLastTraversedText()

    def clear_traversed_text(self):
        '''clear the last traversed text.'''
        self.server.jsonrpc.clearLastTraversedText()

    @property
    def open(self):
        '''
        Open notification or quick settings.
        Usage:
        d.open.notification()
        d.open.quick_settings()
        '''
        @param_to_property(action=["notification", "quick_settings"])
        def _open(action):
            if action == "notification":
                return self.server.jsonrpc.openNotification()
            else:
                return self.server.jsonrpc.openQuickSettings()
        return _open

    @property
    def handlers(self):
        obj = self

        class Handlers(object):

            def on(self, fn):
                if fn not in obj.server.handlers['handlers']:
                    obj.server.handlers['handlers'].append(fn)
                obj.server.handlers['device'] = obj
                return fn

            def off(self, fn):
                if fn in obj.server.handlers['handlers']:
                    obj.server.handlers['handlers'].remove(fn)

        return Handlers()

    @property
    def watchers(self):
        obj = self

        class Watchers(list):

            def __init__(self):
                for watcher in obj.server.jsonrpc.getWatchers():
                    self.append(watcher)

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasAnyWatcherTriggered()

            def remove(self, name=None):
                if name:
                    obj.server.jsonrpc.removeWatcher(name)
                else:
                    for name in self:
                        obj.server.jsonrpc.removeWatcher(name)

            def reset(self):
                obj.server.jsonrpc.resetWatcherTriggers()
                return self

            def run(self):
                obj.server.jsonrpc.runWatchers()
                return self
        return Watchers()

    def watcher(self, name):
        obj = self

        class Watcher(object):

            def __init__(self):
                self.__selectors = []

            @property
            def triggered(self):
                return obj.server.jsonrpc.hasWatcherTriggered(name)

            def remove(self):
                obj.server.jsonrpc.removeWatcher(name)

            def when(self, **kwargs):
                self.__selectors.append(Selector(**kwargs))
                return self

            def click(self, **kwargs):
                obj.server.jsonrpc.registerClickUiObjectWatcher(name, self.__selectors, Selector(**kwargs))

            @property
            def press(self):
                @param_to_property(
                    "home", "back", "left", "right", "up", "down", "center",
                    "search", "enter", "delete", "del", "recent", "volume_up",
                    "menu", "volume_down", "volume_mute", "camera", "power")
                def _press(*args):
                    obj.server.jsonrpc.registerPressKeyskWatcher(name, self.__selectors, args)
                return _press
        return Watcher()

    @property
    def press(self):
        '''
        press key via name or key code. Supported key name includes:
        home, back, left, right, up, down, center, menu, search, enter,
        delete(or del), recent(recent apps), volume_up, volume_down,
        volume_mute, camera, power.
        Usage:
        d.press.back()  # press back key
        d.press.menu()  # press home key
        d.press(89)     # press keycode
        '''
        @param_to_property(
            key=["home", "back", "left", "right", "up", "down", "center",
                 "menu", "search", "enter", "delete", "del", "recent",
                 "volume_up", "volume_down", "volume_mute", "camera", "power"]
        )
        def _press(key, meta=None):
            if isinstance(key, int):
                return self.server.jsonrpc.pressKeyCode(key, meta) if meta else self.server.jsonrpc.pressKeyCode(key)
            else:
                return self.server.jsonrpc.pressKey(str(key))
        return _press

    def wakeup(self):
        '''turn on screen in case of screen off.'''
        self.server.jsonrpc.wakeUp()

    def sleep(self):
        '''turn off screen in case of screen on.'''
        self.server.jsonrpc.sleep()

    @property
    def screen(self):
        '''
        Turn on/off screen.
        Usage:
        d.screen.on()
        d.screen.off()

        d.screen == 'on'  # Check if the screen is on, same as 'd.screenOn'
        d.screen == 'off'  # Check if the screen is off, same as 'not d.screenOn'
        '''
        devive_self = self

        class _Screen(object):
            def on(self):
                return devive_self.wakeup()

            def off(self):
                return devive_self.sleep()

            def __call__(self, action):
                if action == "on":
                    return self.on()
                elif action == "off":
                    return self.off()
                else:
                    raise AttributeError("Invalid parameter: %s" % action)

            def __eq__(self, value):
                info = devive_self.info
                if "screenOn" not in info:
                    raise EnvironmentError("Not supported on Android 4.3 and belows.")
                if value in ["on", "On", "ON"]:
                    return info["screenOn"]
                elif value in ["off", "Off", "OFF"]:
                    return not info["screenOn"]
                raise ValueError("Invalid parameter. It can only be compared with on/off.")

            def __ne__(self, value):
                return not self.__eq__(value)

        return _Screen()

    @property
    def wait(self):
        '''
        Waits for the current application to idle or window update event occurs.
        Usage:
        d.wait.idle(timeout=1000)
        d.wait.update(timeout=1000, package_name="com.android.settings")
        '''
        @param_to_property(action=["idle", "update"])
        def _wait(action, timeout=1000, package_name=None):
            if timeout / 1000 + 5 > int(os.environ.get("JSONRPC_TIMEOUT", 90)):
                http_timeout = timeout / 1000 + 5
            else:
                http_timeout = int(os.environ.get("JSONRPC_TIMEOUT", 90))
            if action == "idle":
                return self.server.jsonrpc_wrap(timeout=http_timeout).waitForIdle(timeout)
            elif action == "update":
                return self.server.jsonrpc_wrap(timeout=http_timeout).waitForWindowUpdate(package_name, timeout)
        return _wait

    def exists(self, **kwargs):
        '''Check if the specified ui object by kwargs exists.'''
        return self(**kwargs).exists


device = AutomatorDevice()
Device = AutomatorDevice
