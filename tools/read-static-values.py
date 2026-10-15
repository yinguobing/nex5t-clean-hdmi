#!/usr/bin/env python3
"""从 dex 的 class_def.static_values 读出 static final 常量的真实值。
   （baksmali 不打印这些值，但它们确实存在 dex 的 encoded_array 里）"""
import struct, sys

VALUE_SIZES = {0x00:1, 0x02:2, 0x03:2, 0x04:4, 0x06:8}
SIGNED      = {0x02, 0x04, 0x06}

def uleb(d, o):
    r = 0; s = 0
    while True:
        b = d[o]; o += 1
        r |= (b & 0x7f) << s
        if not (b & 0x80): break
        s += 7
    return r, o

def read_encoded_array(d, o):
    n, o = uleb(d, o)
    out = []
    for _ in range(n):
        hdr = d[o]; o += 1
        vt, arg = hdr & 0x1f, hdr >> 5
        # 关键：dex 里数值实际占用的字节数是 value_arg + 1，不是固定长度！
        size = arg + 1
        raw = d[o:o+size]; o += size
        if vt not in (0x00, 0x02, 0x03, 0x04, 0x06):
            out.append(('type0x%02x' % vt)); continue
        signed = vt in (0x02, 0x04, 0x06)          # short / int / long 是有符号
        out.append(int.from_bytes(raw, 'little', signed=signed))
    return out

class Dex:
    def __init__(self, d):
        self.d = d
        self.base = d.find(b'dex\n')
        b = self.base
        self.string_ids_size, self.string_ids_off = struct.unpack_from('<II', d, b+0x38)
        self.type_ids_size,   self.type_ids_off   = struct.unpack_from('<II', d, b+0x40)
        self.field_ids_size,  self.field_ids_off  = struct.unpack_from('<II', d, b+0x50)
        self.class_defs_size, self.class_defs_off = struct.unpack_from('<II', d, b+0x60)
    def string(self, i):
        o = struct.unpack_from('<I', self.d, self.base+self.string_ids_off+i*4)[0]
        n, o = uleb(self.d, o)
        return self.d[o:o+n].decode('utf-8','replace')
    def type_name(self, i):
        if i == 0xffffffff: return '?'
        s = struct.unpack_from('<I', self.d, self.base+self.type_ids_off+i*4)[0]
        return self.string(s)
    def field(self, i):
        o = self.base + self.field_ids_off + i*8
        c, t, n = struct.unpack_from('<HHI', self.d, o)
        return self.type_name(c), self.type_name(t), self.string(n)

def dump_class_static_values(dexfile, target_substr):
    d = open(dexfile,'rb').read()
    dx = Dex(d)
    for i in range(dx.class_defs_size):
        o = dx.base + dx.class_defs_off + i*32
        class_idx, access, super_idx, if_off, src_idx, ann_off, cdata_off, sval_off = \
            struct.unpack_from('<IIIIIIII', d, o)
        cname = dx.type_name(class_idx)
        if target_substr not in cname: continue
        print(f'=== {cname} ===')
        if sval_off == 0:
            print('  (没有 static_values —— 常量没有初值或被完全内联)')
            return
        vals = read_encoded_array(d, dx.base + sval_off)
        # 从 class_data 取静态字段顺序
        p = dx.base + cdata_off
        sf, p = uleb(d, p); inf, p = uleb(d, p); sm, p = uleb(d, p); im, p = uleb(d, p)
        idx = 0; statics = []
        for _ in range(sf):
            diff, p = uleb(d, p); acc, p = uleb(d, p)
            idx += diff
            statics.append(dx.field(idx)[2])
        print(f'  静态字段 {len(statics)} 个，static_values {len(vals)} 个')
        for nm, v in zip(statics, vals):
            if isinstance(v, int):
                print(f'    {nm:<34} = {v}  (0x{v & 0xffffffff:x})')
            else:
                print(f'    {nm:<34} = {v}')

if __name__ == '__main__':
    dump_class_static_values(sys.argv[1], sys.argv[2])
