#!/usr/bin/env bash
# generate-cover.sh — 封面生成脚本（Casting-Workflow 原生工具，去品牌）
# 依赖：curl / jq / base64 / 可选 ImageMagick(magick|convert) 或 macOS sips
# 环境变量（调用前 export）：
#   GPT_IMAGE_API_KEY  (必填)   GPT-Image-2 / 兼容代理 key
#   GPT_IMAGE_BASE_URL (可选)   默认 https://api.openai.com/v1
#   GPT_IMAGE_MODEL    (可选)   默认 gpt-image-2
#   GPT_IMAGE_SIZE     (可选)   默认 1024x1536；番茄用 768x1024
#   BOOK_DIR           (必填)   输出目录，建议 ./covers/<书名>
#   PROMPT             (必填)   Step 2 拼好的完整英文提示词
#   REF_IMAGE         (可选)   参考图本地路径或 URL → 走图生图
#   UPLOAD_SIZE        (可选)   平台固定上传像素，如 600x800 → 生成 _上传 版
set -euo pipefail

: "${GPT_IMAGE_API_KEY:?请先 export GPT_IMAGE_API_KEY=你的key}"
: "${PROMPT:?请先 export PROMPT=Step 2 拼好的完整提示词}"
: "${BOOK_DIR:?请先 export BOOK_DIR=./covers/<书名>}"

BASE_URL="${GPT_IMAGE_BASE_URL:-https://api.openai.com/v1}"
MODEL="${GPT_IMAGE_MODEL:-gpt-image-2}"
SIZE="${GPT_IMAGE_SIZE:-1024x1536}"

mkdir -p "$BOOK_DIR/封面"

# 自增版本号，避免覆盖
i=1
while [ -f "$BOOK_DIR/封面/封面_v${i}.png" ]; do i=$((i+1)); done
OUT="$BOOK_DIR/封面/封面_v${i}.png"
RESP="$(mktemp)"
trap 'rm -f "$RESP"' EXIT

if [ -n "${REF_IMAGE:-}" ]; then
  # ---- 图生图 ----
  REF_TMP=""
  trap '[ -n "$REF_TMP" ] && rm -f "$REF_TMP"; rm -f "$RESP"' EXIT
  case "$REF_IMAGE" in
    http://*|https://*)
      REF_TMP="$(mktemp)"
      curl -fsSL --max-time 60 -o "$REF_TMP" "$REF_IMAGE"
      REF_LOCAL="$REF_TMP" ;;
    *)
      [ -f "$REF_IMAGE" ] || { echo "参考图不存在: $REF_IMAGE" >&2; exit 1; }
      REF_LOCAL="$REF_IMAGE" ;;
  esac
  curl -fsS --max-time 240 --retry 2 --retry-delay 5 \
    "$BASE_URL/images/edits" \
    -H "Authorization: Bearer $GPT_IMAGE_API_KEY" \
    --form-string "model=$MODEL" \
    --form-string "size=$SIZE" \
    --form-string "prompt=$PROMPT" \
    -F "image=@$REF_LOCAL" > "$RESP"
else
  # ---- 文生图 ----
  BODY="$(jq -n --arg m "$MODEL" --arg p "$PROMPT" --arg s "$SIZE" \
    '{model:$m, prompt:$p, size:$s}')"
  curl -fsS --max-time 180 --retry 2 --retry-delay 5 \
    "$BASE_URL/images/generations" \
    -H "Authorization: Bearer $GPT_IMAGE_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$BODY" > "$RESP"
fi

if jq -e '.error' "$RESP" >/dev/null 2>&1; then
  echo "API error:" >&2
  jq '.error' "$RESP" >&2
  exit 1
fi

jq -er '.data[0].b64_json // empty' "$RESP" | base64 --decode > "$OUT"
[ -s "$OUT" ] || { echo "empty or malformed output: $OUT" >&2; head -c 300 "$RESP" >&2; exit 1; }

printf '%s\n' "$PROMPT" > "${OUT%.png}.prompt.txt"
[ -n "${REF_IMAGE:-}" ] && printf '%s\n' "$REF_IMAGE" > "${OUT%.png}.ref.txt"

# ---- Step 3.5 平台上传尺寸居中裁剪+缩放 ----
TARGET="${UPLOAD_SIZE:-}"
if [ -n "$TARGET" ] && [ -f "$OUT" ]; then
  UP="${OUT%.png}_上传.png"; W="${TARGET%x*}"; H="${TARGET#*x}"
  if command -v magick >/dev/null 2>&1; then M=magick
  elif command -v convert >/dev/null 2>&1; then M=convert; else M=""; fi
  if [ -n "$M" ]; then
    "$M" "$OUT" -resize "${W}x${H}^" -gravity center -extent "${W}x${H}" "$UP"
  elif command -v sips >/dev/null 2>&1; then
    cp "$OUT" "$UP"
    sw=$(sips -g pixelWidth "$UP" | awk '/pixelWidth/{print $NF}')
    sh=$(sips -g pixelHeight "$UP" | awk '/pixelHeight/{print $NF}')
    if [ $((sw*H)) -ge $((sh*W)) ]; then sips --resampleHeight "$H" "$UP" >/dev/null
    else sips --resampleWidth "$W" "$UP" >/dev/null; fi
    sips -c "$H" "$W" "$UP" >/dev/null
  else
    echo "无 magick/convert/sips，跳过；手动把 $OUT 居中裁剪+缩放到 $TARGET 再上传" >&2
  fi
  [ -f "$UP" ] && file "$UP"
fi

file "$OUT"
ls -lt "$BOOK_DIR/封面/"
