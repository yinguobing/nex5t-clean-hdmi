#!/bin/bash
# 构建 NEX-5T 的 CleanHDMI APP（v2：可用工具链版本）
#
# 关键教训：相机端的安装器对 APK 的打包方式很敏感。
#   用 jarsigner 签名会重写整个 ZIP，导致安装失败（Communication error 100）。
#   必须用 Android 官方工具链：
#     aapt2 link → aapt add → zipalign → apksigner
#   这样 AndroidManifest.xml 在第一个条目、META-INF 在最后，与官方 APP 同构。
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
DL="${ANDROID_TOOLS:-$HOME/dl-android}"   # 工具链目录，见 README
JAVA="$DL/jdk/bin/java"
JAVAC="$DL/jdk/bin/javac"
AAPT2="$DL/aapt2d/aapt2"
AAPT="$DL/bt/android-13/aapt"
ZIPALIGN="$DL/bt/android-13/zipalign"
APKSIGNER="$DL/bt/android-13/apksigner"
ANDROID_JAR="$DL/platform23/android-6.0/android.jar"
R8="$DL/r8.jar"
KS="$DL/cleanhdmi2.keystore"
KSPASS="${CLEANHDMI_KSPASS:?请先设置环境变量 CLEANHDMI_KSPASS（密钥库口令）}"
ALIAS="cleanhdmi"

export PATH="$DL/jdk/bin:$PATH"

APPDIR="${1:-$HERE/app}"
BUILD="$HERE/build-$(basename "$APPDIR")"
OUT="$BUILD/CleanHDMI.apk"
G="$BUILD/gen"

echo "== 1. 清理 =="
rm -rf "$G"; mkdir -p "$G/classes" "$G/dex"

echo "== 2. 编译 Java =="
"$JAVAC" -source 8 -target 8 -nowarn -encoding UTF-8 \
    -classpath "$ANDROID_JAR" -d "$G/classes" \
    $(find "$APPDIR/src" -name "*.java") 2>&1 | grep -v "bootstrap class path" || true
echo "   class: $(find "$G/classes" -name '*.class' | wc -l)"

echo "== 3. dex（d8, min-api 10）=="
"$JAVA" -cp "$R8" com.android.tools.r8.D8 --min-api 10 --release --lib "$ANDROID_JAR" \
    --output "$G/dex" $(find "$G/classes" -name "*.class")
echo "   classes.dex: $(stat -c%s "$G/dex/classes.dex") 字节"

echo "== 4. 资源编译 + 链接 =="
"$AAPT2" compile --dir "$APPDIR/res" -o "$G/res.zip"
"$AAPT2" link -o "$G/base.apk" -I "$ANDROID_JAR" \
    --manifest "$APPDIR/AndroidManifest.xml" "$G/res.zip"
echo "   base.apk: $(stat -c%s "$G/base.apk") 字节"

echo "== 5. 加入 classes.dex（用 aapt add，保持结构）=="
cp "$G/base.apk" "$G/unsigned.apk"
( cd "$G/dex" && "$AAPT" add -f "$G/unsigned.apk" classes.dex >/dev/null )
echo "   unsigned.apk: $(stat -c%s "$G/unsigned.apk") 字节"

echo "== 6. zipalign =="
"$ZIPALIGN" -f 4 "$G/unsigned.apk" "$G/aligned.apk"
"$ZIPALIGN" -c -v 4 "$G/aligned.apk" 2>&1 | tail -2 | sed 's/^/   /'

echo "== 7. apksigner 签名（v1-only, minSdk 10）=="
rm -f "$OUT"
"$APKSIGNER" sign \
    --ks "$KS" --ks-pass "pass:$KSPASS" --key-pass "pass:$KSPASS" --ks-key-alias "$ALIAS" \
    --v1-signing-enabled true --v2-signing-enabled false --v3-signing-enabled false \
    --min-sdk-version 10 --max-sdk-version 18 \
    --out "$OUT" "$G/aligned.apk"

echo
echo "== 8. 校验 =="
"$APKSIGNER" verify --min-sdk-version 10 -v "$OUT" 2>&1 | head -4 | sed 's/^/   /'
"$AAPT2" dump badging "$OUT" 2>/dev/null | head -4 | sed 's/^/   /'
echo "   APK: $(stat -c%s "$OUT") 字节"
python3 - "$OUT" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
print('   条目顺序:', ' → '.join(i.filename for i in z.infolist()))
PY
