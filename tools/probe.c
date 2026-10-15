/*
 * NEX-5T Backup 设置探针（在相机上运行）
 *
 * 为什么完全不使用 libc：
 *   相机系统侧跑的是 glibc 2.9，但被索尼裁剪改名成了 libsonyc.so，
 *   它只导出 899 个符号 —— 有 printf/fopen/malloc，却**没有**
 *   __libc_start_main、stdout、__stack_chk_fail。
 *   同时本机交叉工具链是 glibc 2.43，用它编译会要求 GLIBC_2.34（相机没有）。
 *   所以走最干净的路：自带 _start，只用 svc 系统调用，自己做格式化。
 *
 * 依赖仅剩：
 *   - libbackup.so（相机自带，提供 Backup_get_datasize / Backup_read）
 *   - 加载器 /lib/libsonyld.so（与相机自身二进制一致）
 *
 * 原理：Backup_get_datasize(id) 返回该设置的字节数，ID 不存在则返回错误值。
 *   正对照必须成功、负对照必须失败，二者同时成立才说明这个判定有区分力。
 */

/* 相机 libbackup.so 提供。
 * 注意：它只导出 Backup_get_datasize / Backup_read / Backup_write / Backup_reset 等
 * 16 个函数，**没有** Backup_get_attribute —— 这是链接器实测出来的。 */
extern int Backup_get_datasize(int id);
extern int Backup_read(int id, void *addr);

/* ---- ARM EABI 系统调用 ---- */
#define SYS_exit   1
#define SYS_write  4
#define SYS_open   5
#define SYS_close  6

static int sys3(int n, int a, int b, int c) {
    register int r0 __asm__("r0") = a;
    register int r1 __asm__("r1") = b;
    register int r2 __asm__("r2") = c;
    register int r7 __asm__("r7") = n;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}

#define O_WRONLY 1
#define O_CREAT  64
#define O_TRUNC  512

/* ---- 输出：同时写 stdout 和文件 ---- */
static int fd_out = -1;
static char buf[4096];
static int  blen;

static void flush(void) {
    if (blen > 0) {
        sys3(SYS_write, 1, (int)buf, blen);
        if (fd_out >= 0) sys3(SYS_write, fd_out, (int)buf, blen);
        blen = 0;
    }
}

static void putc_(char c) {
    if (blen >= (int)sizeof buf - 1) flush();
    buf[blen++] = c;
}

static void puts_(const char *s) { while (*s) putc_(*s++); }

static const char HEX[] = "0123456789abcdef";

static void put_hex8(unsigned int v) {
    int i;
    for (i = 28; i >= 0; i -= 4) putc_(HEX[(v >> i) & 0xf]);
}

static void put_dec(int v) {
    char t[12];
    int n = 0;
    unsigned int u;
    if (v < 0) { putc_('-'); u = (unsigned int)(-v); } else u = (unsigned int)v;
    if (u == 0) { putc_('0'); return; }
    while (u && n < (int)sizeof t) { t[n++] = (char)('0' + u % 10); u /= 10; }
    while (n--) putc_(t[n]);
}

/* ---- 探针清单 ---- */
typedef struct { unsigned int id; const char *note; } probe_t;

static const probe_t POSITIVE[] = {
    { 0x01070148, "POS PAL/NTSC" },
    { 0x010d008f, "POS language" },
    { 0x003c0373, "POS reclimit-h" },
    { 0x003c0374, "POS reclimit-m" },
    { 0x003c0375, "POS reclimit-s" },
    { 0x01640001, "POS usb-app-installer" },
    { 0x003e0005, "POS model-name" },
    { 0x00e70000, "POS model-code" },
    { 0x01660024, "POS android-version" },
};

static const probe_t NEGATIVE[] = {
    { 0xdeadbeef, "NEG" },
    { 0x00000000, "NEG" },
    { 0x0107ffff, "NEG" },
    { 0x003cffff, "NEG" },
};

static const probe_t CANDIDATES[] = {
    { 0x010706cc, "cand-A" }, { 0x010706cd, "cand-A" }, { 0x010706ce, "cand-A" },
    { 0x010706cf, "cand-A" }, { 0x010706d0, "cand-A" }, { 0x010706d1, "cand-A" },
    { 0x010706d2, "cand-A" }, { 0x010706d3, "cand-A" }, { 0x010706d4, "cand-A" },
    { 0x010706d5, "cand-A" },
    { 0x0107091d, "cand-B" }, { 0x0107091e, "cand-B" }, { 0x0107091f, "cand-B" },
    { 0x01070920, "cand-B" }, { 0x01070921, "cand-B" }, { 0x01070922, "cand-B" },
    { 0x01070925, "cand-B" }, { 0x01070928, "cand-B" }, { 0x0107092a, "cand-B" },
    { 0x0107092c, "cand-B" },
    { 0x01070933, "cand-C" }, { 0x01070934, "cand-C" },
    { 0x01070937, "cand-C" }, { 0x01070953, "cand-C" },
};

static void do_probe(unsigned int id, const char *note) {
    int size = Backup_get_datasize(id);
    unsigned char val[64];
    int i, show;

    puts_("ID="); put_hex8(id);
    puts_(" SIZE="); put_dec(size);

    if (size > 0 && size <= (int)sizeof val) {
        int rd = Backup_read(id, val);
        puts_(" RD="); put_dec(rd);
        puts_(" VALUE=");
        show = size < 32 ? size : 32;
        for (i = 0; i < show; i++) {
            putc_(HEX[val[i] >> 4]);
            putc_(HEX[val[i] & 0xf]);
        }
    }
    puts_(" NOTE="); puts_(note); putc_('\n');
}

static void run_list(const char *title, const probe_t *p, int n) {
    int i;
    puts_("\n===== "); puts_(title); puts_(" =====\n");
    for (i = 0; i < n; i++) do_probe(p[i].id, p[i].note);
}

/* 十六进制解析（不用 libc 的 strtoul） */
static unsigned int parse_hex(const char *s) {
    unsigned int v = 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) s += 2;
    for (;;) {
        char c = *s++;
        int d;
        if (c >= '0' && c <= '9')      d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else break;
        v = (v << 4) | (unsigned int)d;
    }
    return v;
}

int probe_main(int argc, char **argv) {
    fd_out = sys3(SYS_open, (int)"/tmp/probe-result.txt", O_WRONLY | O_CREAT | O_TRUNC, 0644);

    puts_("probe start\n");

    if (argc >= 3) {
        unsigned int a = parse_hex(argv[1]);
        unsigned int b = parse_hex(argv[2]);
        unsigned int v;
        puts_("sweep "); put_hex8(a); puts_(".."); put_hex8(b); putc_('\n');
        flush();
        v = a;
        for (;;) {
            do_probe(v, "sweep");
            if (blen > 3000) flush();
            if (v == b) break;
            v++;
        }
        puts_("sweep done\n");
    } else {
        run_list("POSITIVE must-succeed",
                 POSITIVE, (int)(sizeof POSITIVE / sizeof POSITIVE[0]));
        run_list("NEGATIVE must-fail",
                 NEGATIVE, (int)(sizeof NEGATIVE / sizeof NEGATIVE[0]));
        run_list("CANDIDATES",
                 CANDIDATES, (int)(sizeof CANDIDATES / sizeof CANDIDATES[0]));
    }

    puts_("probe done\n");
    flush();
    if (fd_out >= 0) sys3(SYS_close, fd_out, 0, 0);
    return 0;
}

/* 自带入口：不依赖 libc 的 crt / __libc_start_main */
__asm__(
    ".global _start\n"
    ".type _start, %function\n"
    "_start:\n"
    "  ldr r0, [sp]\n"        /* argc */
    "  add r1, sp, #4\n"       /* argv */
    "  bl  probe_main\n"
    "  mov r7, #1\n"           /* __NR_exit */
    "  svc #0\n"
    "  b   .\n"
);
