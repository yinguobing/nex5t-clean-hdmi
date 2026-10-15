#!/usr/bin/env python3
"""
L1 实验：把 A99 独有的 5 个属性（0x01070b0c–0x01070b10）嫁接进 NEX-5T 的设置库

格式（完整解出，见 pmca/backup/__init__.py）：
  256 字节头部
  子系统表: numSubsystems × 6 字节  (numProperties:u16, ptr:u32)
  属性表:   numProperties × 5 字节  (attr:u8, ptr:u32)      [revision 2]
  数据区:   偏移是「文件内的绝对偏移」

  ptr 编码 = (size << 24) | offset
    size   = 数据长度（高 8 位）
    offset = 绝对文件偏移（低 24 位）
    size==0    → 变量长属性，offset 处是 u16 size + u16 maxSize
    size==0xff → 超长属性，  offset 处是 u16 size
    attr&0x74  → offset+maxSize 处还有一份等长的「重置值」

ID = (子系统索引 << 16) | 属性在子系统块内的序号

往子系统 0x0107 的块末尾追加 5 项，必须做四件事：
  1) 属性表中间插入 5×5=25 字节  → 数据区整体后移 25 字节
     ⇒ 所有已有属性的绝对偏移必须 +25
  2) 插入点之后所有子系统的 ptr（块起始序号）+5
  3) numProperties +5, dataOffset +25
  4) 新数据追加到文件末尾，新属性按 (size<<24)|offset 编码，重算校验和
"""
import os
import struct
import sys
import warnings

warnings.filterwarnings('ignore')
sys.path.insert(0, '/tmp/pmca-master')
from pmca.backup import BackupFile                      # noqa: E402

SRC = (os.environ.get('FW_DIR', './fw') + '/nex5t/firmware.tar_unpacked/0110_backup/'
       'SYSAVIP-DSLR/RV1/CX76500_ALLLANG.bin')
OUT = os.environ.get('FW_DIR', './fw') + '/nex5t/0110_backup_MODIFIED_HDMI.bin'

HEADER_SIZE = 256
SUBSYS_ENTRY = 6
PROP_ENTRY = 5
SUBSYS_ID = 0x0107
INS_SIZE = 5
SHIFT_BYTES = INS_SIZE * PROP_ENTRY   # 插入的字节数 = 条目数 × 每条 5 字节

# 从 A99 抄来的 5 项：(attr, 数据, 重置值或None)
#   A99 原值: 0x0b0c=500 0x0b0d=500 0x0b0e=500 0x0b0f=0(attr0x60) 0x0b10=65
NEW_PROPS = [
    (0x00, struct.pack('<I', 500), None),
    (0x00, struct.pack('<I', 500), None),
    (0x00, struct.pack('<I', 500), None),
    (0x60, struct.pack('<B', 0),   struct.pack('<B', 0)),   # attr&0x74 → 需要重置值
    (0x00, struct.pack('<I', 65),  None),
]


def main():
    data = bytearray(open(SRC, 'rb').read())

    num_subsys = struct.unpack_from('<I', data, 0x10)[0]
    num_props = struct.unpack_from('<I', data, 0x14)[0]
    data_off = struct.unpack_from('<I', data, 0x18)[0]
    data_size = struct.unpack_from('<I', data, 0x1c)[0]
    print(f'原始: numSubsystems={num_subsys} numProperties={num_props} '
          f'dataOffset={data_off} dataSize={data_size} 文件={len(data)}')

    subsys_off = HEADER_SIZE
    prop_off = subsys_off + num_subsys * SUBSYS_ENTRY

    def get_subsys(i):
        return struct.unpack_from('<HI', data, subsys_off + i * SUBSYS_ENTRY)

    def set_subsys(i, n, p):
        struct.pack_into('<HI', data, subsys_off + i * SUBSYS_ENTRY, n, p)

    def get_prop_ptr(i):
        return struct.unpack_from('<I', data, prop_off + i * PROP_ENTRY + 1)[0]

    def set_prop_ptr(i, ptr):
        struct.pack_into('<I', data, prop_off + i * PROP_ENTRY + 1, ptr)

    n107, ptr107 = get_subsys(SUBSYS_ID)
    print(f'子系统 0x{SUBSYS_ID:04x}: ptr={ptr107} numProperties={n107}')
    assert n107 == 2828, f'预期 2828，实为 {n107}'

    ins_index = ptr107 + n107
    ins_byte = prop_off + ins_index * PROP_ENTRY
    print(f'插入点: 属性序号 {ins_index}, 字节偏移 {ins_byte}')

    for i in range(num_subsys):
        n, p = get_subsys(i)
        if p < ins_index < p + n:
            raise SystemExit(f'子系统 {i} 块跨越插入点，方案不适用')

    # ---- 1) 所有已有属性的绝对偏移 +25 ----
    shifted = 0
    for i in range(num_props):
        ptr = get_prop_ptr(i)
        if ptr == 0xffffffff:
            continue
        size = ptr >> 24
        off = ptr & 0xffffff
        set_prop_ptr(i, (size << 24) | (off + SHIFT_BYTES))
        shifted += 1
    print(f'已调整 {shifted} 个已有属性的数据偏移 (+{INS_SIZE})')

    # ---- 2) 插入 5 个属性表条目（先占位）----
    data[ins_byte:ins_byte] = b'\x00' * (INS_SIZE * PROP_ENTRY)

    # ---- 3) 插入点之后的子系统 ptr +5 ----
    for i in range(num_subsys):
        n, p = get_subsys(i)
        if p >= ins_index:
            set_subsys(i, n, p + INS_SIZE)
    set_subsys(SUBSYS_ID, n107 + INS_SIZE, ptr107)

    # ---- 4) 新数据追加到文件末尾 ----
    for k, (attr, payload, reset) in enumerate(NEW_PROPS):
        off = len(data)
        size = len(payload)
        if size >= 0xff:
            raise SystemExit('本实验不需要超长属性')
        # 固定长度属性：ptr = (size << 24) | offset
        idx = ins_index + k
        struct.pack_into('<B', data, prop_off + idx * PROP_ENTRY, attr)
        struct.pack_into('<I', data, prop_off + idx * PROP_ENTRY + 1,
                         (size << 24) | off)
        data += payload
        if attr & 0x74 and reset is not None:
            data += reset
    new_data_size = len(data) - (data_off + SHIFT_BYTES)

    # ---- 5) 头部计数 ----
    new_data_off = data_off + SHIFT_BYTES
    struct.pack_into('<I', data, 0x14, num_props + INS_SIZE)
    struct.pack_into('<I', data, 0x18, new_data_off)
    struct.pack_into('<I', data, 0x1c, new_data_size)

    # ---- 6) 校验和 ----
    total = new_data_off + new_data_size
    chk = (sum(data[:0x20]) + sum(data[0x24:total])) & 0xFFFFFFFF
    struct.pack_into('<I', data, 0x20, chk)

    open(OUT, 'wb').write(data)
    print(f'\n已写出 {OUT} ({len(data)} 字节)  校验和=0x{chk:08x}')

    # ---- 7) 回读验证 ----
    print('\n===== 回读验证 =====')
    with open(SRC, 'rb') as f:
        orig = {pid: (pr.attr, bytes(pr.data))
                for pid, pr in BackupFile(f).listProperties()}
    with open(OUT, 'rb') as f:
        bf = BackupFile(f)                                   # 顺带校验 checksum
        mod = {pid: (pr.attr, bytes(pr.data))
               for pid, pr in bf.listProperties()}

    print(f'  ✅ 校验和通过，解析成功')
    print(f'  原库 {len(orig)} 项 / 新库 {len(mod)} 项 (差 {len(mod)-len(orig)})')

    # 直接从字节里读子系统表（bf 所在的文件已关闭）
    s_n, s_p = struct.unpack_from('<HI', data, HEADER_SIZE + SUBSYS_ID * SUBSYS_ENTRY)
    print(f'  子系统 0x{SUBSYS_ID:04x}: ptr={s_p} numProperties={s_n} '
          f'→ 最大有效 ID 0x{SUBSYS_ID:04x}{s_n-1:04x}')

    print('\n  新增的 5 项:')
    for idx in range(0x0b0c, 0x0b11):
        tid = (SUBSYS_ID << 16) | idx
        if tid in mod:
            a, d = mod[tid]
            print(f'    0x{tid:08x}  size={len(d):2d} attr=0x{a:02x} data={d.hex()}')
        else:
            print(f'    0x{tid:08x}  ❌ 读不到')

    print('\n  原有属性完整性比对:')
    diff = [k for k in orig if k not in mod or mod[k] != orig[k]]
    new_only = [k for k in mod if k not in orig]
    print(f'    原有 {len(orig)} 项中，值发生变化或丢失的: {len(diff)}')
    if diff:
        for k in diff[:8]:
            print(f'      ⚠️ 0x{k:08x}  原={orig[k][1].hex()} 新={mod.get(k, ("?","?"))[1].hex()}')
    print(f'    新增的 ID: {[hex(k) for k in new_only]}')


if __name__ == '__main__':
    main()
