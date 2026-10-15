#!/usr/bin/env python3
"""
极简 DEX 解析器：从相机 Android 侧的 .odex 里挖出类的完整 API

用途：相机上 com.sony.scalar.* 这些库的接口没有公开文档，
      但 odex 里保留了完整的 dex 结构（字符串表、字段表、方法表、类定义）。
      自己解析就能拿到准确的方法名/字段名，用来反射调用。

odex 格式：前面是 "dey\n036\0" 头，之后就是标准 dex。
"""
import struct
import sys


class Dex:
    def __init__(self, data):
        self.d = data
        # odex 头 "dey\n036\0" 之后是 dex。找 'dex\n' 魔数
        i = data.find(b'dex\n')
        if i < 0:
            raise Exception('找不到 dex 魔数')
        self.base = i
        d = self.d
        b = self.base
        self.string_ids_size, self.string_ids_off = struct.unpack_from('<II', d, b + 0x38)
        self.type_ids_size, self.type_ids_off = struct.unpack_from('<II', d, b + 0x40)
        self.proto_ids_size, self.proto_ids_off = struct.unpack_from('<II', d, b + 0x48)
        self.field_ids_size, self.field_ids_off = struct.unpack_from('<II', d, b + 0x50)
        self.method_ids_size, self.method_ids_off = struct.unpack_from('<II', d, b + 0x58)
        self.class_defs_size, self.class_defs_off = struct.unpack_from('<II', d, b + 0x60)

    # ---- 基础 ----
    def uleb(self, off):
        d = self.d
        b = self.base
        result = 0
        shift = 0
        p = b + off
        while True:
            x = d[p]
            p += 1
            result |= (x & 0x7f) << shift
            if not (x & 0x80):
                break
            shift += 7
        return result, p - b

    def string(self, idx):
        if idx >= self.string_ids_size:
            return '?'
        off = struct.unpack_from('<I', self.d, self.base + self.string_ids_off + idx * 4)[0]
        n, p = self.uleb(off)
        raw = self.d[self.base + p: self.base + p + n]
        return raw.decode('utf-8', 'replace')

    def type_name(self, idx):
        if idx == 0xffffffff or idx >= self.type_ids_size:
            return '?'
        s = struct.unpack_from('<I', self.d, self.base + self.type_ids_off + idx * 4)[0]
        return self.string(s)

    def field(self, idx):
        o = self.base + self.field_ids_off + idx * 8
        cls, typ, name = struct.unpack_from('<HHI', self.d, o)
        return self.type_name(cls), self.type_name(typ), self.string(name)

    def method(self, idx):
        o = self.base + self.method_ids_off + idx * 8
        cls, proto, name = struct.unpack_from('<HHI', self.d, o)
        return self.type_name(cls), self.string(name), proto

    def proto(self, idx):
        o = self.base + self.proto_ids_off + idx * 12
        shorty, ret, params_off = struct.unpack_from('<III', self.d, o)
        params = []
        if params_off:
            n = struct.unpack_from('<I', self.d, self.base + params_off)[0]
            for k in range(n):
                t = struct.unpack_from('<H', self.d, self.base + params_off + 4 + k * 2)[0]
                params.append(self.type_name(t))
        return self.type_name(ret), params

    # ---- 类 ----
    def classes(self):
        for i in range(self.class_defs_size):
            o = self.base + self.class_defs_off + i * 32
            class_idx, access, super_idx, ifaces, src, ann, cdata, sval = \
                struct.unpack_from('<IIIIIIII', self.d, o)
            yield self.type_name(class_idx), access, cdata

    def dump_class(self, want):
        for cname, access, cdata in self.classes():
            if want not in cname:
                continue
            print(f'\n===== {cname}  (access={access:#x}) =====')
            if not cdata:
                print('  (无类数据)')
                continue
            p = cdata
            sf, p = self.uleb(p)
            inf, p = self.uleb(p)
            sm, p = self.uleb(p)
            im, p = self.uleb(p)
            print(f'  静态字段 {sf} / 实例字段 {inf} / 直接方法 {sm} / 虚方法 {im}')

            def rd_fields(count, label):
                nonlocal p
                if not count:
                    return
                print(f'  --- {label} ---')
                idx = 0
                for _ in range(count):
                    diff, p = self.uleb(p)
                    acc, p = self.uleb(p)
                    idx += diff
                    _, typ, nm = self.field(idx)
                    print(f'      {typ:<34} {nm}')

            def rd_methods(count, label):
                nonlocal p
                if not count:
                    return
                print(f'  --- {label} ---')
                idx = 0
                for _ in range(count):
                    diff, p = self.uleb(p)
                    acc, p = self.uleb(p)
                    code, p = self.uleb(p)
                    idx += diff
                    _, nm, proto = self.method(idx)
                    ret, params = self.proto(proto)
                    plist = ', '.join(x.split('/')[-1].rstrip(';') for x in params)
                    print(f'      {ret:<30} {nm}({plist})')

            rd_fields(sf, '静态字段')
            rd_fields(inf, '实例字段')
            rd_methods(sm, '直接方法')
            rd_methods(im, '虚方法')


def main():
    path = sys.argv[1]
    want = sys.argv[2] if len(sys.argv) > 2 else 'DisplayManager'
    data = open(path, 'rb').read()
    dx = Dex(data)
    print(f'dex: strings={dx.string_ids_size} types={dx.type_ids_size} '
          f'fields={dx.field_ids_size} methods={dx.method_ids_size} '
          f'classes={dx.class_defs_size}')
    dx.dump_class(want)


if __name__ == '__main__':
    main()
