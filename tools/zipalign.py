#!/usr/bin/env python3
"""极简 zipalign：重写 zip，把未压缩条目的数据对齐到 4 字节"""
import sys, zipfile, struct, zlib

def align(src, dst, A=4):
    zin = zipfile.ZipFile(src)
    out = open(dst, 'wb')
    centrals = []
    for info in zin.infolist():
        data = zin.read(info.filename)
        comp = info.compress_type
        if comp == zipfile.ZIP_STORED:
            payload = data
        else:
            co = zlib.compressobj(9, zlib.DEFLATED, -15)   # ZIP 要 raw deflate，不是 zlib 格式
            payload = co.compress(data) + co.flush()
        name = info.filename.encode('utf-8')
        extra = b''
        if comp == zipfile.ZIP_STORED:
            base = out.tell() + 30 + len(name)
            pad = (-base) % A
            if pad:
                if pad >= 4:
                    extra = struct.pack('<HH', 0xFFFF, pad - 4) + b'\0' * (pad - 4)
                else:
                    extra = b'\0' * pad
        crc = zlib.crc32(data) & 0xffffffff
        off = out.tell()
        out.write(struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, 0, comp,
                              info.date_time[3], info.date_time[4], crc,
                              len(payload), len(data), len(name), len(extra)))
        out.write(name); out.write(extra); out.write(payload)
        centrals.append((name, comp, crc, len(payload), len(data), off, extra, info.date_time))
    cd = out.tell()
    for name, comp, crc, csz, usz, off, extra, dt in centrals:
        out.write(struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, 20, 0, comp,
                              dt[3], dt[4], crc, csz, usz, len(name), len(extra),
                              0, 0, 0, 0, off))
        out.write(name); out.write(extra)
    out.write(struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, len(centrals), len(centrals),
                          out.tell() - cd, cd, 0))
    out.close()
    z = zipfile.ZipFile(dst)
    bad = [i.filename for i in z.infolist()
           if i.compress_type == 0 and (i.header_offset + 30 + len(i.filename) + len(i.extra)) % A]
    print(f'  {src} → {dst}   未压缩条目未对齐数: {len(bad)} {bad if bad else ""}')

if __name__ == '__main__':
    align(sys.argv[1], sys.argv[2])
