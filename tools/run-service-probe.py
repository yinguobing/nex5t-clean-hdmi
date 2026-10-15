#!/usr/bin/env python3
"""
NEX-5T service mode 探针驱动

为什么走 service mode 而不是 updater mode：
  updater mode 需要让相机重启进固件更新流程，而索尼的更新流程在 NEX-5T 上
  会弹出「恢复相机默认设置」要求确认 —— 那会重置相机设置。
  service mode 的设计目的是"在运行中的系统上执行代码"（PMCA-RE README 原话），
  不重启、不重置，所以安全得多。

前置条件：相机必须处于【海量存储器 (MSC)】USB 模式
          （菜单 → 设置 → USB连接 → 海量存储器）

流程：进入 service mode → 上传 probe → 终端执行 → 回收输出与结果文件
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PMCA_SRC = os.path.expanduser('~/.local/opt/pmca-re/src')
if PMCA_SRC not in sys.path:
    sys.path.insert(0, PMCA_SRC)

import warnings
warnings.filterwarnings('ignore')

from pmca.commands.usb import importDriver, getDevice, listDevices          # noqa: E402
from pmca.usb.sony import (                                                  # noqa: E402
    SonyMscExtCmdDevice, SonySenserDevice, SonySenserAuthDevice, SonySenserCamera,
)

PROBE_LOCAL = os.path.join(HERE, 'probe')
PROBE_REMOTE = '/tmp/probe'
RESULT_REMOTE = '/tmp/probe-result.txt'
RESULT_LOCAL = os.path.join(HERE, 'probe-result-remote.txt')
MARKER = b'===PROBE-EXIT==='


def drain(device, seconds):
    """收集终端输出若干秒"""
    out = bytearray()
    end = time.time() + seconds
    while time.time() < end:
        d = device.readTerminal()
        if d:
            out += d
        else:
            time.sleep(0.05)
    return out


def wait_marker(device, timeout):
    out = bytearray()
    end = time.time() + timeout
    while time.time() < end:
        d = device.readTerminal()
        if d:
            out += d
            if MARKER in out:
                return out, True
        else:
            time.sleep(0.05)
    return out, False


def main():
    if not os.path.exists(PROBE_LOCAL):
        print('[!] 没找到 probe，请先运行 ./build.sh')
        return 1
    payload = open(PROBE_LOCAL, 'rb').read()
    print(f'[+] 探针 {len(payload)} 字节')

    driver_name = 'libusb'
    with importDriver(driver_name) as driver:
        device = getDevice(driver)
        if not device:
            print('[!] 没找到相机')
            return 1
        print(f'[+] 检测到: {type(device).__name__}')

        if not isinstance(device, SonyMscExtCmdDevice):
            print('[!] 相机必须是【海量存储器】模式')
            print('    菜单 → 设置 → USB连接 → 海量存储器')
            return 1

        print('[+] 请求进入 service mode（相机不重启、不重置）…')
        auth = SonySenserAuthDevice(device.driver)
        auth.start()
        auth.authenticate()

        device = None
        for _ in range(40):
            time.sleep(0.5)
            try:
                ds = list(listDevices(driver, True))
                if len(ds) == 1 and isinstance(ds[0], SonySenserDevice):
                    device = ds[0]
                    break
            except Exception:                                        # noqa: BLE001
                pass
        if device is None:
            print('[!] 超时：相机没有切到 service mode')
            return 1
        print('[+] 已进入 service mode')

        auth = SonySenserAuthDevice(device.driver)
        auth.start()
        auth.authenticate()
        try:
            cam = SonySenserCamera(device)
            # readHasp 只是读 HASP 加密狗信息，对本测试无用；NEX-5T 上返回 128，直接跳过
            try:
                cam.readHasp()
                print('[+] readHasp OK')
            except Exception as e:                                   # noqa: BLE001
                print(f'[!] readHasp 失败（不致命，继续）: {e}')

            print(f'[+] 上传探针到 {PROBE_REMOTE} …')
            cam.writeFile(PROBE_REMOTE, payload)
            time.sleep(1.0)

            print('[+] 打开终端并执行…')
            cam.setTerminalEnable(False)
            cam.setTerminalEnable(True)
            time.sleep(0.5)
            drain(device, 0.5)

            cmd = (b'echo ===BEGIN===; '
                   b'chmod +x ' + PROBE_REMOTE.encode() + b' && '
                   + PROBE_REMOTE.encode() + b'; '
                   b'echo ' + MARKER + b'\n')
            device.writeTerminal(cmd)

            out, ok = wait_marker(device, 120)
            print('\n---------- 相机终端输出 ----------')
            sys.stdout.write(out.decode('latin1', 'replace'))
            print('\n---------- 输出结束 ----------')
            if not ok:
                print('[!] 没等到结束标记（可能还在跑或已卡住）')

            print(f'[+] 取回 {RESULT_REMOTE} …')
            got = False
            for attempt in range(3):
                try:
                    with open(RESULT_LOCAL, 'wb') as f:
                        cam.readFile(RESULT_REMOTE, f)
                    if os.path.getsize(RESULT_LOCAL) > 0:
                        got = True
                        break
                except Exception as e:                               # noqa: BLE001
                    print(f'    取文件失败 ({type(e).__name__}: {e})，重试…')
                    time.sleep(1)
            if got:
                print(f'[+] 已保存 {RESULT_LOCAL} ({os.path.getsize(RESULT_LOCAL)} 字节)')
            else:
                print('[!] 没能取回结果文件（终端输出里应该也有内容）')

            try:
                cam.setTerminalEnable(False)
            except Exception:                                        # noqa: BLE001
                pass
        finally:
            auth.stop()
            print('[+] 已退出 service mode')

    return 0


if __name__ == '__main__':
    sys.exit(main())
