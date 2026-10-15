#!/usr/bin/env python3
"""
在 service mode 下用 readFile 探明相机的分区布局（纯只读，不写任何东西）

目的：搞清「设置数据放在哪个分区 / 怎么被加载」，才能判断
      把修改过的 Backup.bin 送进去是否安全、以及走哪条路。
"""

import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/tmp/pmca-master')

import warnings
warnings.filterwarnings('ignore')

from pmca.commands.usb import importDriver, getDevice, listDevices          # noqa: E402
from pmca.usb.sony import (                                                  # noqa: E402
    SonyMscExtCmdDevice, SonySenserDevice, SonySenserAuthDevice, SonySenserCamera,
)

FILES = [
    '/proc/mounts',
    '/proc/partitions',
    '/proc/version',
    '/proc/cmdline',
    '/proc/devices',
]


def try_read(cam, path):
    try:
        buf = io.BytesIO()
        cam.readFile(path, buf)
        d = buf.getvalue()
        if not d:
            return None
        return d
    except Exception as e:                                       # noqa: BLE001
        print(f'  ❌ {path}: {type(e).__name__}: {e}')
        return None


def main():
    with importDriver('libusb') as driver:
        device = getDevice(driver)
        if not device:
            print('[!] 没找到相机'); return 1
        if not isinstance(device, SonyMscExtCmdDevice):
            print('[!] 相机必须是【海量存储器】模式'); return 1

        print('[+] 进入 service mode…')
        auth = SonySenserAuthDevice(device.driver)
        auth.start(); auth.authenticate()
        device = None
        for _ in range(40):
            time.sleep(0.5)
            try:
                ds = list(listDevices(driver, True))
                if len(ds) == 1 and isinstance(ds[0], SonySenserDevice):
                    device = ds[0]; break
            except Exception:                                    # noqa: BLE001
                pass
        if device is None:
            print('[!] 超时'); return 1
        print('[+] 已进入 service mode\n')

        auth = SonySenserAuthDevice(device.driver)
        auth.start(); auth.authenticate()
        try:
            cam = SonySenserCamera(device)
            for path in FILES:
                print(f'===== {path} =====')
                d = try_read(cam, path)
                if d:
                    try:
                        txt = d.decode('utf-8', 'replace')
                    except Exception:                            # noqa: BLE001
                        txt = repr(d[:400])
                    print(txt[:2000])
                else:
                    print('  (空)')
                print()
        finally:
            auth.stop()
            print('[+] 已退出 service mode')
    return 0


if __name__ == '__main__':
    sys.exit(main())
