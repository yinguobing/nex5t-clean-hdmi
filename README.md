# NEX-5T 干净 HDMI 输出

> **给索尼 NEX-5T 一个没有 OSD 叠加的 HDMI 画面** —— 一个 11.6 KB 的 PMCA 应用，不改固件、不改设置、卸载即恢复。

[![相机](https://img.shields.io/badge/机型-Sony%20NEX--5T-informational)]()
[![固件](https://img.shields.io/badge/固件-1.00-informational)]()
[![APK](https://img.shields.io/badge/APK-11.6%20KB-success)]()
[![下载](https://img.shields.io/github/v/release/yinguobing/nex5t-clean-hdmi?label=%E4%B8%8B%E8%BD%BD&color=brightgreen)](https://github.com/yinguobing/nex5t-clean-hdmi/releases/latest)

---

## 这是什么

NEX-5T 通过 HDMI 输出时，画面上会强制叠加一层信息（快门/光圈/ISO/曝光挡位）。

- **菜单里没有关掉它的选项** —— 索尼只在 A99 等高端机型上提供了「HDMI Info. Display」
- **DISP 键切到「无显示信息」也去不掉** —— 底部那条信息栏仍然强制显示
- **所以它没法用来直播或干净录制**

这个项目用一个自制应用解决了它：**应用运行时，相机的取景器渲染停止，那层 OSD 根本不参与渲染。**

配合一个几十块的 HDMI 采集卡，就能在 PC 上拿到干净画面做直播/录制。

---

## 快速开始

### 1. 相机设置（一次性）

```
设置 → 宽影像 → 全屏        # 消掉画面黑边
```

### 2. 安装应用

**从 [Releases](https://github.com/yinguobing/nex5t-clean-hdmi/releases/latest) 下载 `CleanHDMI.apk`**，
然后用 PMCA 工具装到相机（相机需处于 MTP 模式）：

```bash
pmca-console install -f CleanHDMI.apk
```

PMCA 工具：[Sony-PMCA-RE](https://github.com/ma1uta/Sony-PMCA-RE) / [pmca-console](https://github.com/ThirteenAG/Sony-PMCA-RE)

> **下载后建议校验**（Release 页面附有 SHA-256）：
> ```bash
> sha256sum CleanHDMI.apk
> ```
>
> 想自己构建的话，见下面的「[自己构建](#自己构建)」。

### 3. 使用

```
应用程序列表 → 干净画面 → 运行
```

| 项目 | 结果 |
|---|---|
| overlay | **完全没有** |
| 画面比例 | 全屏，完整视野无裁切 |
| 画质 | ISP 处理后的成品画质 |
| 退出 | **按 MENU**（或电源键正常关机） |

---

## ⚠️ 重要：使用注意

**这个应用会独占相机。** 所以下面几件事必须知道：

### 按键行为

| 按键 | 行为 |
|---|---|
| **MENU** | 退出应用 |
| **快门（半按 / 全按）** | ✅ **放行给相机**，正常对焦 / 拍摄 |
| **其余所有按键** | **一律退出应用** |

> **为什么是"其余一律退出"？**
> 相机系统自己也在读按键。如果让「播放图像」「MOVIE」这类会切换界面的键透传给相机系统，
> 它会和独占相机的应用**争抢相机** → 黑屏 → 系统重启 → 重启后自动恢复上次的应用 → 再次争抢 → **死循环**。
>
> 实测复现过：**卡死时连电源键都失效，只能取出电池。**

**详见 [`docs/上篇-合作纪实.md`](docs/上篇-合作纪实.md) 第八节。**

### 出问题了怎么恢复

```
1. 取出电池（电源键无效时唯一办法）
2. 等 10 秒
3. 装回电池，开机
4. 相机应正常落到拍摄界面
```

### 其他

- **关机前建议先按 MENU 退出应用**（应用已在 `onPause` 时释放相机，但先退出更保险）
- **应用运行时无法用 MOVIE 键录制** —— 录制界面会和应用抢显示
- **删除应用后相机完全恢复原样** —— 不改固件、不改设置

---

## 原理

### 相机的显示分两层

```
┌─────────────────────────────────────────┐
│  视频层（硬件层）                        │
│    · 相机实时画面，按相机自己的分辨率    │
├─────────────────────────────────────────┤
│  图形层（UI 层）                         │
│    · 相机 OSD（快门/光圈/ISO）           │
│    · 菜单、PMCA 应用界面                 │
└─────────────────────────────────────────┘
              ↓ 合成 → LCD / HDMI
```

**关键**：相机的 OSD 属于图形层，**只在"拍摄界面"状态下被绘制**。

一旦有应用占屏，相机进入"应用界面"状态 —— **取景器渲染整个停止，那层 OSD 从来就没被画出来过。**

所以应用只要「把实时画面显示出来 + 上面什么都不画」，HDMI 上就是干净的实时画面。

### 核心调用序列

```java
// 1) onCreate：SurfaceHolder 必须设 PUSH_BUFFERS
holder.setType(SurfaceHolder.SURFACE_TYPE_PUSH_BUFFERS);  // ★ 缺这行 startPreview 必失败
holder.setFormat(PixelFormat.RGBA_8888);

// 2) 反射打开相机（不需要索尼 SDK）
Class<?> c  = Class.forName("com.sony.scalar.hardware.CameraEx");
Class<?> oo = Class.forName("com.sony.scalar.hardware.CameraEx$OpenOptions");
Object cameraEx = c.getMethod("open", int.class, oo).invoke(null, 0, null);
Camera camera = (Camera) c.getMethod("getNormalCamera").invoke(cameraEx);
holder.addCallback(this);

// 3) surfaceCreated
camera.setPreviewDisplay(holder);
camera.startPreview();
```

### 相机按键扫描码

从固件 `com.sony.scalar.sysutil.ScalarInput` 的 `static_values` 读出：

| 按键 | 扫描码 | 状态 |
|---|---|---|
| 快门半按 | `0x204` | ✅ 已验证 |
| 快门全按 | `0x206` | ✅ 已验证 |
| 播放图像 | `0xcf` | ✅ 已验证（交叉验证） |
| 确定 | `0xe8` | ✅ 已验证（交叉验证） |
| 菜单 | `0x202` | ⚠️ **此值存疑**，实测菜单键不是它 |

> **⚠️ 不要逐键硬编码扫描码。**
> 上面这套值只在**确定键**和**播放键**上被交叉验证过。我们曾经据此把「菜单键 = `0x202`」写死，
> 结果翻车（MENU 退出失效、相机的菜单被打开）。
> **现在的做法是白名单：只放行快门，其余一律退出 —— 猜错的最坏结果是"多退出一次"，而不是死循环。**

---

## 自己构建

### 依赖

| 组件 | 说明 |
|---|---|
| JDK 17 | `javac` |
| `android.jar`（platform-23） | 编译用的 API 桩 |
| Android build-tools | `aapt2` / `aapt` / `zipalign` / `apksigner` |
| `r8.jar`（D8） | class → dex |

把工具链放在一个目录里（默认 `~/dl-android`，可用 `ANDROID_TOOLS` 覆盖）：

```
$ANDROID_TOOLS/
├── jdk/                    # JDK 17
├── aapt2d/aapt2
├── bt/android-13/{aapt,zipalign,apksigner}
├── platform23/android-6.0/android.jar
└── r8.jar
```

### ⚠️ 打包方式很关键

相机端的安装器**对 APK 的打包方式非常敏感**。用 `jarsigner` 签名会重写整个 ZIP 导致安装失败
（报 `Communication error 100`）。**必须用官方工具链**：

```
aapt2 compile / link  →  aapt add（塞 classes.dex）  →  zipalign  →  apksigner（v1-only）
```

产出的 APK 结构应与官方 APP 同构：

```
AndroidManifest.xml → 资源 → classes.dex → META-INF/（签名在最后）
```

### 生成自己的密钥库

仓库**不包含**密钥库。首次构建前先生成一个：

```bash
keytool -genkeypair -keystore my.keystore \
  -storepass <你的口令> -keypass <你的口令> -alias cleanhdmi \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=CleanHDMI, OU=NEX5T, O=NEX5T, C=CN"
```

然后：

```bash
export CLEANHDMI_KSPASS='<你的口令>'
./tools/build-apk.sh ../app          # 产物在 build-app/CleanHDMI.apk
```

---

## 仓库结构

```
├── README.md                  本文
├── docs/
│   ├── 上篇-合作纪实.md        这场攻坚的完整故事（含我们各自做对了什么）
│   └── 下篇-技术细节.md        固件分析 / 备份格式 / DEX 常量提取 / 打包要求 / 踩坑速查
├── app/                       ★ 最终应用源码
│   ├── AndroidManifest.xml
│   ├── res/
│   └── src/com/nex5t/cleanhdmi/MainActivity.java
├── experiments/
│   └── clean-osd/             死路实验：DisplayManager.controlGraphicsOutputAll()
└── tools/                     构建脚本与逆向调查工具
```

> **构建好的 APK 在 [Releases](https://github.com/yinguobing/nex5t-clean-hdmi/releases) 里**，不放在仓库内
> —— 避免二进制进 git 历史，也避免两份副本日后不一致。

### 调查工具

| 工具 | 用途 |
|---|---|
| `dexdump.py` | 极简 DEX 解析器 —— 从相机 `.odex` 挖类/方法/字段签名 |
| `read-static-values.py` | 读 dex 的 `static_values`，还原 `static final` 常量值（按键表来源） |
| `run-readbackup.py` | service mode 下按 ID 读设置（内置正/负对照） |
| `run-service-probe.py` | service mode 自动化驱动 |
| `probe.c` | 自包含 ARM 探针（相机 `libsonyc.so` 无 `__libc_start_main`，只能裸机写） |
| `build-modified-backup.py` | `Backup.bin` 结构改写（属性跨机型嫁接） |
| `fetch-models.sh` | 多机型固件批量下载 + 解包流水线 |
| `build-apk.sh` | 一键构建（含全部工具链步骤） |
| `make-icon.py` | 图标生成器（超采样抗锯齿） |

---

## 已确证的结论

**1. NEX-5T 的固件不支持「HDMI Info. Display」—— 不是隐藏，是没有**

| 证据 | 内容 |
|---|---|
| 索尼规格表 | 该行标为不支持 |
| 设置库解析 | NEX-5T 的 `0x0107` 子系统 2828 项；A99 有 2833 项，多出的 5 项正是 A99 独有的 HDMI 设置 |
| **实机查询** | `readBackup(0x01070b0f)` 返回 `error 129`，与随机 ID 反应一致；正对照全部成功 |

**2. 改固件也没用**

造出了嫁接版 `Backup.bin`（把 A99 那 5 个属性移植进 NEX-5T，13494 个原有属性字节级一致），
但静态分析显示：**两台机器的固件里都没有任何代码引用那个设置 ID** —— 加进去也是死的。

**3. `DisplayManager.controlGraphicsOutputAll(false)` 不能用**

它关掉的是**整个显示输出**而不是叠加层。关掉后画面全黑，约 10 秒后看门狗强制重启。
（`experiments/clean-osd/` 就是这个实验）

---

## 走过的死路

| 路线 | 为什么不通 |
|---|---|
| gphoto2 抓 live view | libgphoto2 不支持 NEX-5T，回落通用 PTP |
| Sony Camera Remote API | 需要 PMCA 应用，官方下载服务 2025 年 8 月已停止；且 live view 是低分辨率 MJPEG |
| Cascable Pro Webcam | 支持 NEX-5T，但只支持 macOS |
| 找隐藏的 HDMI 设置 | 固件里确实没有（三条证据） |
| 改固件加这个设置 | 没有代码引用它，改了也不生效 |
| `setPreviewSize` 提高画质 | `getSupportedPreviewSizes()` 返回 null |
| 把 SurfaceView 做大提高画质 | 只影响图形层，视频层不受影响 |
| `controlGraphicsOutputAll(false)` | 关的是整个显示输出，会导致相机重启 |
| "任意键退出"一刀切 | 会把快门也吃掉 |
| 逐键硬编码扫描码 | 猜错就失效（菜单键翻车） |

**详见 [`docs/下篇-技术细节.md`](docs/下篇-技术细节.md) 第十节的 16 条踩坑速查表。**

---

## 说明

- 本仓库**不包含**任何索尼固件、索尼官方 APK 或从固件中提取的符号清单
- 所有结论均在真机上验证，而非推测
- 应用只调用相机自身提供的公开 Java 接口，**不修改固件、不修改设置**
- 风险自负：应用会独占相机，使用前请阅读上面的「使用注意」

## 许可

代码部分：MIT
文档部分：CC BY 4.0

---

*本项目的完整过程记录在 [`docs/`](docs/) 的两篇文章里。*
