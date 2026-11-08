#!/bin/zsh
# Third cut of the submission video, 2026-11-07. What the first two got wrong and this one fixes:
#  - the camera and screen recorders were two ffmpeg processes; their clocks drift by about 13 ms per second
#    (measured with demo/xcorr_v3.py: cross-correlation of the two mic tracks every 5 s). Each kept segment
#    takes the camera from in+lag(in) to out+lag(out) and stretches it to the screen clock, audio always from
#    the screen file.
#  - in-points come from mlx-whisper word times (0.35 s before the first word of the final read, 0.5 s after
#    the last), silences over 0.8 s inside a read are cut, alternate segments are punched in 6%.
#  - the camera file is portrait; the face is cropped square (1080x1080 at y=420) for the 360 px picture in
#    picture; shot 6 is full frame on a blurred fill.
#  - overlays are PIL PNGs timed to the word that names them; the score card is built, not borrowed.
# Run order: words.py on each screen file -> xcorr_v3.py per shot -> build_v3.py -> loudnorm two-pass.
set -e
W=~/Movies/partial-demo-2026-11-07/v3/work; mkdir -p $W
cd $W
for s in shot1 shot2 shot3 shot6; do
  f=$(ls ~/CODELocalProjects/partial/demo/takes/$s/screen-*.mp4)
  HF_HUB_OFFLINE=1 ~/.local/bin/uv run --with mlx-whisper python ~/.claude/skills/demo-video/scripts/words.py "$f" $s-words.json
  for k in screen camera; do ffmpeg -nostdin -v error -y -i $(ls ~/CODELocalProjects/partial/demo/takes/$s/$k-*.mp4) -vn -ac 1 -ar 48000 -c:a pcm_s16le $s-$k.wav; done
  ~/.local/bin/uv run --with numpy python ~/CODELocalProjects/partial/demo/xcorr_v3.py $s   # paste the rows into LAG in build_v3.py
done
~/.local/bin/uv run --with numpy --with pillow python ~/CODELocalProjects/partial/demo/build_v3.py
cd ~/Movies/partial-demo-2026-11-07/v3
ffmpeg -nostdin -i out/raw.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p'   # then the second pass with measured_* values
