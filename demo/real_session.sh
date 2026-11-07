#!/bin/zsh
# real_session.sh: take the newest real on-body block from silent-speech-cerelog, damage a copy, let the agent
# on the Meta Model API reconstruct it, score it against the untouched copy, and keep the three outputs
# (never the tape, never the key) under examples/real-run-<stamp>/.
# Usage: ./real_session.sh [--fake-model]       exit 2 when no real block exists yet.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/.." && pwd)
SSC=${SSC:-$HOME/CODELocalProjects/silent-speech-cerelog}
FAKE=${1:-}
src=$(ls -td "$SSC"/data/sat/*_sat-b1 2>/dev/null | head -1 || true)
if [[ -z "$src" || ! -f "$src/tape.bin" ]]; then
  echo "no real block yet: nothing under $SSC/data/sat/*_sat-b1 with a tape.bin. Record one first (python -m ssc record ...)."; exit 2
fi
stamp=$(date +%Y%m%d-%H%M%S)
real="$REPO/data/real-$stamp"; dmg="$real-damaged"; out="$REPO/examples/real-run-$stamp"
mkdir -p "$real" "$out"
for f in tape.bin meta.json events.csv reads.csv; do
  [[ -f "$src/$f" ]] && cp "$src/$f" "$real/" || echo "  note: $src has no $f"
done
echo "real session copied from $src -> $real ($(du -sh "$real" | cut -f1))"
cd "$REPO"; source .venv/bin/activate; set -a; [[ -f .env ]] && source .env; set +a
partial corrupt "$real" --out "$dmg" | tee "$out/log.txt"
if [[ "$FAKE" == "--fake-model" ]]; then partial reconstruct "$dmg" --fake-model | tee -a "$out/log.txt"
else partial reconstruct "$dmg" | tee -a "$out/log.txt"; fi
partial score "$dmg" --truth "$real" | tee -a "$out/log.txt"
cp "$dmg/reconstruction.json" "$out/" 2>/dev/null || echo "  no reconstruction.json produced"
cp "$dmg/parse_tape.py" "$out/" 2>/dev/null || true
cp "$dmg"/figures/*.png "$out/" 2>/dev/null || true
cp "$dmg".damage.json "$out/damage.json" 2>/dev/null || true
cp "$real/meta.json" "$out/truth_meta.json"; cp "$real/events.csv" "$out/truth_events.csv"
sed -i '' -E 's/LLM_[A-Za-z0-9_.-]+/LLM_<redacted>/g' "$out/log.txt"
grep -l -E "LLM_[A-Za-z0-9]{10}" "$out"/* 2>/dev/null && { echo "a key leaked into $out; refusing"; exit 3; }
echo "kept: $out (tape stays in $real, git-ignored)"; ls "$out"
