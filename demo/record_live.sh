#!/bin/zsh
# record_live.sh start | stop | status
# Screen of the Mac 48 + FaceTime camera as a picture-in-picture (bottom-left, a quarter wide) + microphone.
# Output: demo/screen-<stamp>.mp4 (screen + mic) and demo/camera-<stamp>.mp4 (camera + mic), separate files for the edit.
# Device indices measured on forge-m5-48, 2026-11-07, ffmpeg 9.0.2 (`ffmpeg -f avfoundation -list_devices true -i ""`):
#   video [0] MacBook Pro Camera   [1] Desk View Camera   [2] Capture screen 0
#   audio [0] MacBook Pro Microphone   [1] LoomAudioDevice
# Override with SCREEN_DEV, CAM_DEV, MIC_DEV if the list changes. Run it in a Terminal window on the 48 itself:
# the first run asks for Screen Recording and Camera permission for Terminal, which an ssh shell cannot answer.
# KNOWN FLAW (2026-11-07, measured in the edit): two separate ffmpeg processes drift apart by about 13 ms per
# second (camera relative to screen), so a fixed offset is 1 s wrong after 80 s. The v3 edit measured the lag every
# 5 s by cross-correlating the two mic tracks and stretched the camera onto the screen clock (demo/xcorr_v3.py).
# The real fix, not yet built: one ffmpeg with both inputs and two outputs (-map per output), so both files share
# a clock, or a visible clap at the start of every take.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PIDFILE="$HERE/.record_live.pid"
SCREEN_DEV=${SCREEN_DEV:-2}; CAM_DEV=${CAM_DEV:-0}; MIC_DEV=${MIC_DEV:-0}
FPS=${FPS:-30}; PIP_W=${PIP_W:-480}; PAD=24

start() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cut -d" " -f1 "$PIDFILE")" 2>/dev/null; then
    echo "already recording (pids $(cat "$PIDFILE")); run: $0 stop"; exit 1
  fi
  if pgrep -f "ffmpeg -nostdin -hide_banner -loglevel warning -f avfoundation" >/dev/null; then
    echo "a recorder from an earlier run is still alive; run: $0 stop (it kills strays)"; exit 1
  fi
  local stamp scr cam
  stamp=$(date +%Y%m%d-%H%M%S); scr="$HERE/screen-$stamp.mp4"; cam="$HERE/camera-$stamp.mp4"
  local secs="${1:-}"; local dur=()
  [[ -n "$secs" ]] && dur=(-t "$secs")
  # ONE ffmpeg, three inputs, two outputs. Both files get the same mic track and start on the same clock, so the
  # edit can use a fixed offset of zero. (2026-11-07: two separate processes drifted 13 ms/s apart and the first
  # two cuts were out of sync.) Separate files are kept on purpose: the edit composes them (Carl, 2026-11-07).
  ffmpeg -nostdin -hide_banner -loglevel warning \
    -f avfoundation -framerate "$FPS" -capture_cursor 1 -pixel_format uyvy422 -i "${SCREEN_DEV}:none" \
    -f avfoundation -framerate "$FPS" -pixel_format uyvy422 -i "${CAM_DEV}:none" \
    -f avfoundation -i "none:${MIC_DEV}" \
    -map 0:v -map 2:a -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p" \
      -c:v h264_videotoolbox -b:v 8M -r "$FPS" -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000 \
      -movflags +frag_keyframe+empty_moov "${dur[@]}" "$scr" \
    -map 1:v -map 2:a -c:v h264_videotoolbox -b:v 8M -r "$FPS" -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000 \
      -movflags +frag_keyframe+empty_moov "${dur[@]}" "$cam" \
    >"$HERE/.record_live.log" 2>&1 &
  local p1=$!
  echo "$p1" > "$PIDFILE"
  sleep 3
  if ! kill -0 $p1 2>/dev/null; then echo "ffmpeg died at start:"; tail -5 "$HERE/.record_live.log"; rm -f "$PIDFILE"; exit 2; fi
  echo "recording -> $scr + $cam (pid $p1, one clock). Stop with: $0 stop"
}

stop() {
  [[ -f "$PIDFILE" ]] || { echo "not recording"; exit 1; }
  local pids; pids=$(cat "$PIDFILE")
  # 2026-11-07: SIGINT alone left three recorder pairs running for five minutes and the later screen captures
  # failed on a busy device. Escalate: INT, then TERM, then KILL, and refuse to leave any of ours alive.
  for sig in INT TERM KILL; do
    for pid in $pids; do kill -$sig "$pid" 2>/dev/null; done
    for i in {1..20}; do local alive=0; for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive=1; done; (( alive )) || break; sleep 0.25; done
    (( alive )) || break
  done
  rm -f "$PIDFILE"
  local left; left=$(pgrep -f "ffmpeg -nostdin -hide_banner -loglevel warning -f avfoundation" | wc -l | tr -d " ")
  (( left == 0 )) || { echo "WARNING: $left recorder process(es) still alive; killing all of them"; pkill -KILL -f "ffmpeg -nostdin -hide_banner -loglevel warning -f avfoundation"; }
  for f in $(ls -t "$HERE"/screen-*.mp4 "$HERE"/camera-*.mp4 2>/dev/null | head -2); do
    echo "stopped. file: $f"
    ffprobe -v error -show_entries stream=codec_type,codec_name,width,height -show_entries format=duration -of default=nw=1 "$f" 2>/dev/null
  done
}

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cut -d" " -f1 "$PIDFILE")" 2>/dev/null; then echo "recording (pids $(cat "$PIDFILE"))"; else echo "idle"; fi
}

case "${1:-}" in
  start) start "${2:-}" ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 start [seconds] | stop | status"; exit 64 ;;
esac
