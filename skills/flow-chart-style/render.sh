#!/usr/bin/env bash
# render.sh <name|path>   ->  <name>.svg  (+ <name>.png when possible)
#
# 為什麼要這支腳本：
#   Kroki 的 SVG 光柵器 (resvg) 會誤套 Mermaid base 主題裡 [data-look="neo"]
#   的 filter:drop-shadow 規則，讓節點卡片出現陰影。這裡在取得 SVG 後把所有
#   drop-shadow 濾鏡改成 none，確保「不加陰影」。
#
# 優先用本機 mmdc（字型正確、可直接出 PNG）；沒有 mmdc 就走 Kroki（免安裝，
# 需要 curl），PNG 步驟再另找 headless Chrome / Chromium。
#
# 提示：build_flow.py 已內建這整套流程（含自動樣式）。這支腳本適合「.mmd
#       已經是完整樣式、只想輸出圖檔」的情況。

set -eu
here="$(cd "$(dirname "$0")" && pwd)"
config="${FLOW_CHART_CONFIG:-$here/flow-chart.mermaid.json}"

arg="${1:-}"
if [ -z "$arg" ]; then echo "用法: ./render.sh diagram   (或 diagram.mmd / 路徑)" >&2; exit 2; fi
base="${arg%.mmd}"
name="$(basename "$base")"
mmd="$base.mmd"
svg="$base.svg"
png="$base.png"
[ -f "$mmd" ] || { echo "找不到 $mmd" >&2; exit 2; }

# ---- 路線 A：本機 mmdc ------------------------------------------------------
if command -v mmdc >/dev/null 2>&1; then
  cf=(); [ -f "$config" ] && cf=(--configFile "$config")
  mmdc "${cf[@]}" -i "$mmd" -o "$svg" -b '#F7F7F7'
  echo "OK  (mmdc) -> $svg"
  mmdc "${cf[@]}" -i "$mmd" -o "$png" -b '#F7F7F7' -w 2048 && echo "OK  (mmdc) -> $png"
  exit 0
fi

# ---- 路線 B：Kroki -------------------------------------------------------- #
command -v curl >/dev/null 2>&1 || { echo "需要 mmdc 或 curl 其中之一" >&2; exit 1; }
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
code=""
for i in 1 2 3 4 5 6 7 8; do
  code="$(curl -s -o "$svg" -w '%{http_code}' -A "$UA" --max-time 60 -X POST \
          -H 'Content-Type: text/plain' --data-binary "@${mmd}" \
          https://kroki.io/mermaid/svg 2>/dev/null | tr -cd '0-9')"
  [ -n "$code" ] || code="000"
  [ "$code" = "200" ] && break
  echo "Kroki 回應 $code，${i}/8 重試中…" >&2
  sleep $((2 + i))
done
if [ "$code" != "200" ]; then
  echo "Kroki 匯出失敗（$code）：" >&2; head -c 400 "$svg" >&2; echo >&2; exit 1
fi

# 去陰影：filter:drop-shadow(...) -> filter:none
python3 - "$svg" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = re.sub(r'filter\s*:\s*drop-shadow\((?:[^()]|\([^()]*\))*\)', 'filter:none', s)
open(p, 'w', encoding="utf-8").write(s)
PY
echo "OK  (kroki) -> $svg"

# ---- SVG -> PNG（headless Chrome / Chromium；沒有就略過）------------------ #
CHROME=""
for c in "${PUPPETEER_EXECUTABLE_PATH:-}" "${CHROME_PATH:-}" "${CHROME:-}" \
         "$(command -v google-chrome 2>/dev/null || true)" \
         "$(command -v google-chrome-stable 2>/dev/null || true)" \
         "$(command -v chromium 2>/dev/null || true)" \
         "$(command -v chromium-browser 2>/dev/null || true)" \
         "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
  if [ -n "$c" ] && [ -x "$c" ]; then CHROME="$c"; break; fi
done

if [ -n "$CHROME" ]; then
  html="$(mktemp -t "${name}").html"
  python3 - "$svg" "$html" <<'PY'
import sys
svg = open(sys.argv[1], encoding="utf-8").read()
open(sys.argv[2], 'w', encoding="utf-8").write(
  '<!doctype html><meta charset=utf-8>'
  '<style>*{margin:0}body{background:#fff;display:inline-block}svg{display:block}</style>' + svg)
PY
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --default-background-color=FFFFFFFF --force-device-scale-factor=3 \
    --window-size=1400,4000 --screenshot="$png" "file://$html" 2>/dev/null || true
  rm -f "$html"
  if [ -f "$png" ] && python3 -c "import PIL" 2>/dev/null; then
    python3 - "$png" <<'PY'
import sys
from PIL import Image, ImageChops
im = Image.open(sys.argv[1]).convert("RGB")
bg = Image.new("RGB", im.size, (255, 255, 255))
bbox = ImageChops.difference(im, bg).getbbox()
if bbox:
    m = 24
    im.crop((max(0, bbox[0]-m), max(0, bbox[1]-m),
             min(im.width, bbox[2]+m), min(im.height, bbox[3]+m))).save(sys.argv[1])
PY
  fi
  [ -f "$png" ] && echo "OK  (chrome) -> $png" || echo "（PNG 產生失敗，略過）"
else
  echo "（略過 PNG：找不到 mmdc 或 Chrome/Chromium）"
fi
