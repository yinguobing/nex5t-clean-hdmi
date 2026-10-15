#!/usr/bin/env python3
"""生成 APP 图标：取景框 + 干净画面带的极简设计（4x 超采样抗锯齿）"""
import zlib, struct, math, sys

def render(S):
    """返回 S x S 的 RGB 像素（用 0.0-1.0 的浮点色）"""
    px = [[(0.0,0.0,0.0) for _ in range(S)] for _ in range(S)]
    cx = cy = S/2.0
    R  = S*0.19          # 圆角半径
    BG = (0.055,0.062,0.078)      # 近黑背景
    GR = (0.180,0.816,0.416)      # 品牌绿
    GR2= (0.100,0.560,0.290)
    for y in range(S):
        for x in range(S):
            fx, fy = x+0.5, y+0.5
            # ---- 圆角方底 ----
            dx = max(abs(fx-cx) - (S/2.0 - R - 2), 0.0)
            dy = max(abs(fy-cy) - (S/2.0 - R - 2), 0.0)
            d  = math.hypot(dx,dy) - R
            if d > 0.5:  px[y][x] = (0,0,0); continue
            col = BG
            # 背景微渐变
            t = fy/S
            col = (BG[0]+0.020*t, BG[1]+0.026*t, BG[2]+0.034*t)
            # ---- 四角取景框（L 形）----
            m   = S*0.155           # 边距
            L   = S*0.205           # 角臂长
            T   = S*0.062           # 线宽
            inX = m <= fx <= S-m
            inY = m <= fy <= S-m
            def arm(signx, signy):
                # 水平臂
                x0,x1 = (m, m+L) if signx<0 else (S-m-L, S-m)
                y0,y1 = (m, m+T) if signy<0 else (S-m-T, S-m)
                if x0<=fx<=x1 and y0<=fy<=y1: return True
                # 垂直臂
                x0,x1 = (m, m+T) if signx<0 else (S-m-T, S-m)
                y0,y1 = (m, m+L) if signy<0 else (S-m-L, S-m)
                if x0<=fx<=x1 and y0<=fy<=y1: return True
                return False
            if arm(-1,-1) or arm(1,-1) or arm(-1,1) or arm(1,1):
                col = GR
            # ---- 中间的「干净画面」带 ----
            by0, by1 = cy - S*0.105, cy + S*0.105
            bx0, bx1 = m + S*0.10, S - m - S*0.10
            if by0 <= fy <= by1 and bx0 <= fx <= bx1:
                col = GR2
                # 高光线
                if abs(fy - (by0+S*0.022)) < S*0.012:
                    col = (0.55,0.98,0.68)
            px[y][x] = col
    return px

def downsample(px, S, f):
    """从 S 超采样到 S//f"""
    n = S//f
    out = [[(0.0,0.0,0.0)]*n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            r=g=b=0.0
            for j in range(f):
                for i in range(f):
                    c = px[y*f+j][x*f+i]
                    r+=c[0]; g+=c[1]; b+=c[2]
            k = f*f
            out[y][x] = (r/k, g/k, b/k)
    return out

def write_png(path, px):
    n = len(px)
    raw = bytearray()
    for y in range(n):
        raw.append(0)
        for x in range(n):
            r,g,b = px[y][x]
            raw += bytes((int(r*255+0.5), int(g*255+0.5), int(b*255+0.5)))
    def chunk(t, d):
        return struct.pack('>I',len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d)&0xffffffff)
    png  = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    open(path,'wb').write(png)
    return len(png)

if __name__ == '__main__':
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 144
    out    = sys.argv[2] if len(sys.argv) > 2 else 'icon.png'
    S, f = target*3, 3
    px = downsample(render(S), S, f)
    n = write_png(out, px)
    print(f'  {out}: {target}x{target}, {n} 字节')
