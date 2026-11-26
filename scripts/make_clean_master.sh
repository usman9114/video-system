#!/usr/bin/env bash
# One command: branded WFP source -> clean master (no end card, logo inpainted, new captions, levelled audio).
#
#   scripts/make_clean_master.sh source/<file>.mp4 [out_name]
#
# Steps (each is skipped if its output already exists for this source):
#   1. audio-only WAV  -> Kaggle 2xT4: Whisper large-v3 word timestamps  -> assets/transcripts/<name>.words.json
#   2. lossless crop around the logo + mask -> Kaggle 2xT4: LaMa inpaint  -> kaggle/outputs/kgpu-inpaint-logo/...
#   3. local: panel + captions + loudnorm + x264 veryslow CRF14           -> exports/<out_name>.mp4
# Regions/timings live in templates/clean_master.json. Lessons: docs/LESSONS.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SRC="${1:?usage: make_clean_master.sh source.mp4 [out_name]}"
NAME="${2:-clean_master}"
BASE="$(basename "${SRC%.*}")"
CFG=templates/clean_master.json
WORK="kaggle/work/$BASE"; mkdir -p "$WORK" assets/transcripts exports
IFS=x read -r W H < <(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$SRC")
eval "$(python3 - "$CFG" "$W" "$H" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1])); W, H = int(sys.argv[2]), int(sys.argv[3])
bx, by = c["base_size"]; sx, sy = W / bx, H / by
pc, lg = c["logo_patch_crop"], c["logo_box"]; pad = pc.get("mask_pad", 6)
ev = lambda v: int(round(v / 8.0)) * 8          # LaMa wants multiples of 8
cw, ch = ev(pc["w"] * sx), ev(pc["h"] * sy)
cx, cy = min(round(pc["x"] * sx), W - cw), round(pc["y"] * sy)
print(f"TRIM={c['trim_end']} CW={cw} CH={ch} CX={cx} CY={cy}")
print(f"MX0={round(lg['x']*sx)-cx-pad} MY0={round(lg['y']*sy)-cy-pad} "
      f"MX1={round((lg['x']+lg['w'])*sx)-cx+pad} MY1={round((lg['y']+lg['h'])*sy)-cy+pad}")
EOF
)"
echo "source ${W}x${H}, trim ${TRIM}s, logo crop ${CW}x${CH}+${CX}+${CY}"

# 1. transcript (audio only leaves this machine)
TR="assets/transcripts/$BASE.words.json"
if [ ! -f "$TR" ]; then
  ffmpeg -hide_banner -loglevel error -y -i "$SRC" -t "$TRIM" -vn -ac 1 -ar 16000 "$WORK/$BASE.wav"
  bin/kgpu run jobs/transcribe --input "$WORK/$BASE.wav" --timeout-min 20
  cp "kaggle/outputs/kgpu-transcribe/out/$BASE.words.json" "$TR"
fi

# 2. logo inpainting (only a small crop around the logo leaves this machine, not the face)
PATCH="$WORK/inpainted.mkv"
if [ ! -f "$PATCH" ]; then
  ffmpeg -hide_banner -loglevel error -y -t "$TRIM" -i "$SRC" -an -vf "crop=$CW:$CH:$CX:$CY" -c:v ffv1 -pix_fmt rgb24 "$WORK/crop.mkv"
  python3 -c "from PIL import Image, ImageDraw; m=Image.new('L',($CW,$CH),0); ImageDraw.Draw(m).rectangle([$MX0,$MY0,$MX1,$MY1],fill=255); m.save('$WORK/mask.png')"
  bin/kgpu run jobs/inpaint-logo --input "$WORK/crop.mkv" --input "$WORK/mask.png" --timeout-min 30
  cp kaggle/outputs/kgpu-inpaint-logo/out/inpainted.mkv "$PATCH"
fi

# 3. local high-quality render
python3 scripts/clean_master.py "$SRC" "$TR" "exports/$NAME.mp4" --logo-patch "$PATCH"
echo "QA:"; ffmpeg -hide_banner -nostats -i "exports/$NAME.mp4" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I|Peak):"
ffmpeg -hide_banner -nostats -i "exports/$NAME.mp4" -vf "blackdetect=d=0.1:pix_th=0.08,freezedetect=n=0.003:d=0.8" -an -f null - 2>&1 \
  | grep -E "black_start|freeze_start" || echo "  no black or frozen frames"
