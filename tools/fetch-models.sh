#!/bin/bash
# 多机型对比流水线：下载固件 → 7z 提取 FirmwareData → fwtool 解包 → 解析 backup
# 目的：验证 A99 独有的 0x01070b0c–0x01070b10 那一簇，是不是跟「HDMI Info. Display」相关
set -u

P="${HTTPS_PROXY:-}"        # 需要代理时自行设置，例如 http://127.0.0.1:8080
ZA="$HOME/.local/opt/7zip/usr/lib/7zip/7z"
VENV="$HOME/.local/opt/pmca-re/venv"
FT=/tmp/fwtool/fwtool.py
OUT="$HOME/fw/multimodel"
mkdir -p "$OUT"

# 机型 → dmg 直链（都从固件页取到的真实地址）
MODELS="SLT-A77 NEX-7 DSC-RX100M2 SLT-A65"
url_of() {
  case "$1" in
    SLT-A77)      echo "https://support.d-imaging.sony.co.jp/download/DSLR/XAewAIbXf5/Update_SLTA77V107.dmg" ;;
    NEX-7)        echo "https://support.d-imaging.sony.co.jp/download/NEX/yPM9KL6Nlx/Update_NEX7V103.dmg" ;;
    DSC-RX100M2)  echo "https://support.d-imaging.sony.co.jp/download/DSC/42ojqKfsFe/Update_DSCRX100M2V110.dmg" ;;
    SLT-A65)      echo "https://support.d-imaging.sony.co.jp/download/DSLR/yoy7bEo0sA/Update_SLTA65V107.dmg" ;;
  esac
}

for M in $MODELS; do
  echo "########## $M ##########"
  U="$(url_of "$M")"
  if [ ! -s "$OUT/$M.dmg" ]; then
    curl -sSL -x "$P" --max-time 2400 -A "Mozilla/5.0" \
      -e "https://support.d-imaging.sony.co.jp/www/cscs/firm/?mdl=$M&area=jp&lang=jp" \
      -o "$OUT/$M.dmg" "$U?fm=jp" -w "  下载 http=%{http_code} size=%{size_download}\n"
  else
    echo "  已有 dmg: $(stat -c%s "$OUT/$M.dmg") 字节"
  fi

  echo "  7z 提取…"
  "$ZA" x -y "$OUT/$M.dmg" -o"$OUT/$M" >/dev/null 2>&1
  DAT="$(find "$OUT/$M" -name 'FirmwareData_*.dat' 2>/dev/null | head -1)"
  if [ -z "$DAT" ]; then
    echo "  ❌ 没找到 FirmwareData_*.dat"
    continue
  fi
  echo "  DAT: $(basename "$DAT") ($(stat -c%s "$DAT") 字节)"

  echo "  fwtool 解包…"
  rm -rf "$OUT/$M/unpacked"
  "$VENV/bin/python" "$FT" unpack -f "$DAT" -o "$OUT/$M/unpacked" >/dev/null 2>&1
  BK="$(find "$OUT/$M/unpacked/firmware.tar_unpacked/0110_backup" -name '*.bin' 2>/dev/null | head -1)"
  echo "  backup: ${BK:-未找到}"
  [ -n "$BK" ] && echo "  ✅ $M 就绪"
done

echo
echo "########## 汇总 ##########"
for M in $MODELS; do
  BK="$(find "$OUT/$M/unpacked/firmware.tar_unpacked/0110_backup" -name '*.bin' 2>/dev/null | head -1)"
  printf "  %-14s %s\n" "$M" "${BK:-失败}"
done
