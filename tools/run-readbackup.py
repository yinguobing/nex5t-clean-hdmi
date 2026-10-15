#!/usr/bin/env python3
"""
终审：在 NEX-5T 上直接问相机「0x01070b0f 这个设置存在吗」

为什么这是终审：
  前面的差分只能说明「A99 的默认设置库里多了 0x01070b0f」。
  但固件默认数据 ≠ 固件支持范围 —— 一个设置可能被支持却没进默认库。

  上游 PMCA-RE master 提供了服务模式下的 AdjustControl backup 接口：
     SONY_ADJUST_BACKUP_READ  = (0x603, 1)   →  readBackup(id)
     SONY_ADJUST_BACKUP_WRITE = (0x603, 2)   →  writeBackup(id, data)

  直接调用它才是确定答案：
    - 返回数据   → 这台相机支持该设置 → 可以写入 → 干净 HDMI 有戏
    - 报错       → 不支持 → 结论明确

前置：相机处于【海量存储器】模式；已装 udev 规则
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 用上游 master 的代码（本地 v0.18 没有 readBackup/writeBackup）
PMCA_MASTER = '/tmp/pmca-master'
if PMCA_MASTER not in sys.path:
    sys.path.insert(0, PMCA_MASTER)

import warnings
warnings.filterwarnings('ignore')

from pmca.commands.usb import importDriver, getDevice, listDevices          # noqa: E402
from pmca.usb.sony import (                                                  # noqa: E402
    SonyMscExtCmdDevice, SonySenserDevice, SonySenserAuthDevice, SonySenserCamera,
)

# ---- 待查清单 ----
KNOWN = [                      # 正对照：确定存在的设置
    (0x01070148, 'PAL/NTSC 选择器'),
    (0x003c0373, '录像时长 时'),
    (0x010706cc, '候选A 之一'),
]
NEGATIVE = [                   # 负对照：确定不存在
    (0xdeadbeef, '乱编'),
    (0x0107ffff, '越界'),
]
SUBJECT = [                    # 待判定：A99 独有、1 字节、attr=0x60
    (0x01070b0f, '★ HDMI Info. Display 候选'),
    (0x01070b0c, 'A99独有 同簇'),
    (0x01070b0d, 'A99独有 同簇'),
    (0x01070b0e, 'A99独有 同簇'),
    (0x01070b10, 'A99独有 同簇'),
]


def show(tag, cam, id, note):
    try:
        data = cam.readBackup(id)
        if isinstance(data, str):
            data = data.encode('latin1')
        print(f'  [{tag}] 0x{id:08x}  ✅ 存在  {len(data):4d} 字节  {data[:24].hex()}   {note}')
        return data
    except Exception as e:                                       # noqa: BLE001
        print(f'  [{tag}] 0x{id:08x}  ❌ {type(e).__name__}: {e}   {note}')
        return None


def main():
    with importDriver('libusb') as driver:
        device = getDevice(driver)
        if not device:
            print('[!] 没找到相机'); return 1
        print(f'[+] {type(device).__name__}')
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
        print('[+] 已进入 service mode')

        auth = SonySenserAuthDevice(device.driver)
        auth.start(); auth.authenticate()
        try:
            cam = SonySenserCamera(device)

            print('\n===== 正对照（必须成功）=====')
            for i, n in KNOWN:
                show('POS', cam, i, n)

            print('\n===== 负对照（必须失败）=====')
            for i, n in NEGATIVE:
                show('NEG', cam, i, n)

            print('\n===== 待判定：HDMI Info. Display =====')
            got = None
            for i, n in SUBJECT:
                r = show('???', cam, i, n)
                if r is not None and i == 0x01070b0f:
                    got = r

            print('\n########## 结论 ##########')
            if got is not None:
                print(f'  ★ 0x01070b0f 在 NEX-5T 上存在！({len(got)} 字节, 值 {got.hex()})')
                print('    → 固件支持该设置，只是没在菜单里暴露')
                print('    → 可以尝试写入 01 打开它')
            else:
                print('  0x01070b0f 在 NEX-5T 上不存在')
                print('    → 该设置未被这台相机的固件支持')
        finally:
            auth.stop()
            print('[+] 已退出 service mode')
    return 0


if __name__ == '__main__':
    sys.exit(main())
