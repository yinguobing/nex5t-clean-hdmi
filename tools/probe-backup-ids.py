#!/usr/bin/env python3
"""
NEX-5T Backup 设置 ID 探针

原理：PMCA-RE 的 updatershell 能让相机进入"固件更新模式"并在其中执行代码。
     该模式暴露了 libbackup.so 的 Backup_read(id)，对应命令 BKRD。

      对每个候选 ID 调用 BKRD：
        - 返回字节 => 该设置在这台相机上真实存在
        - 抛异常   => 不存在

      同时查询"正对照"（确定存在的设置）和"负对照"（乱编的 ID），
      用来验证这套判定确实有区分力。

用法：
    ./probe-backup-ids.py              # 用内置的 ID 清单
    ./probe-backup-ids.py ids.txt      # 用文件里的清单（每行一个十六进制 ID，# 后为注释）
    ./probe-backup-ids.py --plan       # 只打印将要查询什么，不碰相机
"""

import io
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIST = os.path.join(HERE, 'probe-ids.txt')

PMCA_SRC = os.path.expanduser('~/.local/opt/pmca-re/src')
if PMCA_SRC not in sys.path:
    sys.path.insert(0, PMCA_SRC)

import warnings
warnings.filterwarnings('ignore')

# ---- ID 清单 ---------------------------------------------------------------
GROUPS = [
    ('正对照（确定存在，必须成功）', [
        0x01070148,   # PAL/NTSC 选择器
        0x010d008f,   # 语言
        0x003c0373,   # 录像时长 时
        0x01640001,   # USB app 安装器
        0x003e0005,   # 机型名
    ]),
    ('负对照（确定不存在，必须失败）', [
        0xdeadbeef,
        0x00000000,
        0x0107ffff,
    ]),
    ('候选组 A：viewUnified4.so 中的连续 ID 数组', [
        0x010706cc, 0x010706cd, 0x010706ce, 0x010706cf, 0x010706d0,
        0x010706d1, 0x010706d2, 0x010706d3, 0x010706d4, 0x010706d5,
    ]),
    ('候选组 B：{ID, attr, 0/1} 布尔形状条目', [
        0x0107091d, 0x0107091e, 0x0107091f, 0x01070920, 0x01070921,
        0x01070922, 0x01070925, 0x01070928, 0x0107092a, 0x0107092c,
    ]),
    ('候选组 C：被相机侧模块引用的', [
        0x01070933, 0x01070934, 0x01070937, 0x01070953,
    ]),
]


def load_ids(path):
    groups = []
    cur = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if not line:
                continue
            try:
                v = int(line, 16)
            except ValueError:
                # 当作分组标题
                cur = (line, [])
                groups.append(cur)
                continue
            if cur is None:
                cur = ('未分组', [])
                groups.append(cur)
            cur[1].append(v)
    return groups


def show_plan(groups):
    total = sum(len(ids) for _, ids in groups)
    for title, ids in groups:
        print(f'\n=== {title}  ({len(ids)} 个) ===')
        for v in ids:
            print(f'  0x{v:08x}')
    print(f'\n共 {total} 个 ID，将逐个执行 BKRD 查询。')


def probe(groups):
    from pmca.commands.usb import importDriver, getDevice, getFdat, firmwareUpdateCommandInternal
    from pmca.usb.usbshell import UpdaterShellBackend
    from pmca.usb.sony import SonyExtCmdCamera

    results = {}

    def complete(device):
        be = UpdaterShellBackend(device)
        be.waitReady()
        print('\n[+] updater shell 就绪，开始查询\n', flush=True)
        for title, ids in groups:
            print(f'\n===== {title} =====', flush=True)
            for v in ids:
                try:
                    data = be.readBackup(v)
                    raw = bytes(bytearray(ord(c) for c in data)) if isinstance(data, str) else bytes(data)
                    hexs = ' '.join('%02x' % b for b in raw)
                    results[v] = raw
                    print(f'  0x{v:08x}  OK   {len(raw):4d} 字节   {hexs[:80]}', flush=True)
                except Exception as e:                       # noqa: BLE001
                    results[v] = None
                    print(f'  0x{v:08x}  --   {type(e).__name__}: {e}', flush=True)
        try:
            be.exit()
        except Exception:                                    # noqa: BLE001
            pass

    with importDriver() as driver:
        device = getDevice(driver)
        if not device:
            print('[!] 没找到相机。请插上 USB，并确保处于 MTP 模式。')
            return 1
        print('[+] 相机已识别，读取机型名…')
        try:
            model = SonyExtCmdCamera(device).getCameraInfo().modelName
        except Exception as e:                                   # noqa: BLE001
            print(f'[!] 读不到机型名: {e}')
            return 1
        print(f'[+] 机型: {model}')
        fdat = getFdat(model)
        if not fdat:
            print(f'[!] 没有 {model} 的 FDAT')
            return 1
        print(f'[+] FDAT 已装载（{len(fdat)} 字节）')

        # 自己实现切换流程：PMCA-RE 内置的只等 30 秒，这里延长到 5 分钟，
        # 因为相机的 LCD 上会出现需要人工确认的提示。
        from pmca.usb.sony import SonyUpdaterCamera, SonyUpdaterDevice
        from pmca.commands.usb import listDevices as _listDevices
        from pmca.io import ProgressFile

        f = io.BytesIO(fdat)
        dev = SonyUpdaterCamera(device)
        print('[+] 初始化固件更新接口…')
        dev.init()
        dev.checkGuard(f, len(fdat))
        f.seek(0)

        print('\n' + '=' * 64)
        print('  ⚠️  现在请盯着相机屏幕，按上面出现的提示操作！')
        print('      （很可能要你按某个键确认进入更新模式）')
        print('      最长等待 5 分钟。')
        print('=' * 64 + '\n', flush=True)

        dev.switchMode()

        newdev = None
        for _i in range(600):
            time.sleep(0.5)
            try:
                ds = list(_listDevices(driver, True))
                if len(ds) == 1 and isinstance(ds[0], SonyUpdaterDevice):
                    newdev = ds[0]
                    break
            except Exception:                                    # noqa: BLE001
                pass

        if not newdev:
            print('[!] 5 分钟内相机没有切换到 updater 模式。')
            return 1

        print('[+] 相机已进入 updater 模式，写入 shell payload…')
        dev2 = SonyUpdaterCamera(newdev)
        dev2.writeFirmware(ProgressFile(f, len(fdat)), len(fdat), complete)
        dev2.complete()
        print('[+] 完成')

    # 汇总
    print('\n\n########## 汇总 ##########')
    ok = [v for v, d in results.items() if d]
    bad = [v for v, d in results.items() if d is None]
    print(f'存在 {len(ok)} 个 / 不存在 {len(bad)} 个')
    for title, ids in groups:
        print(f'\n--- {title} ---')
        for v in ids:
            d = results.get(v, 'NOT-QUERIED')
            if d == 'NOT-QUERIED':
                print(f'  0x{v:08x}  (未查询)')
            elif d is None:
                print(f'  0x{v:08x}  不存在')
            else:
                print(f'  0x{v:08x}  存在  {len(d)} 字节  ' + ' '.join('%02x' % b for b in d[:32]))
    return 0


def main():
    args = [a for a in sys.argv[1:] if a != '--plan']
    groups = load_ids(args[0]) if args else GROUPS
    if '--plan' in sys.argv:
        show_plan(groups)
        return 0
    return probe(groups)


if __name__ == '__main__':
    sys.exit(main())
