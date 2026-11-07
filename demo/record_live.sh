#!/bin/zsh
# record_live.sh start | stop | status
# Screen of the Mac 48 + FaceTime camera as a picture-in-picture (bottom-left, a quarter wide) + microphone.
# Output: demo/screen-<stamp>.mp4 (screen + mic) and demo/camera-<stamp>.mp4 (camera + mic), separate files for the edit.
# Device indices measured on forge-m5-48, 2026-11-07, ffmpeg 9.0.2 (`ffmpeg -f avfoundation -list_devices true -i ""`):
#   video [0] MacBook Pro Camera   [1] Desk View Camera   [2] Capture screen 0
#   audio [0] MacBook Pro Microphone   [1] LoomAudioDevice
# Override with SCREEN_DEV, CAM_DEV, MIC_DEV if the list changes. Run it in a Terminal window on the 48 itself:
# the first run asks for Screen Recording and Camera permission for Terminal, which an ssh shell cannot answer.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PIDFILE="$HERE/.record_live.pid"
SCREEN_DEV=${SCREEN_DEV:-2}; CAM_DEV=${CAM_DEV:-0}; MIC_DEV=${MIC_DEV:-0}
FPS=${FPS:-30}; PIP_W=${PIP_W:-480}; PAD=24

start() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cut -d" " -f1 "$PIDFILE")" 2>/dev/null; then
    echo "already recording (pids $(cat "$PIDFILE")); run: $0 stop"; exit 1
  fi
  local stamp scr cam
  stamp=$(date +%Y%m%d-%H%M%S); scr="$HERE/screen-$stamp.mp4"; cam="$HERE/camera-$stamp.mp4"
  local secs="${1:-}"; local dur=()
  [[ -n "$secs" ]] && dur=(-t "$secs")
  # Two separate files, both with the mic track so they can be aligned in the edit (Carl, 2026-11-07:
  # "keep the camera and the screen separate MP4 so you can edit them post").
  ffmpeg -nostdin -hide_banner -loglevel warning \
    -f avfoundation -framerate "$FPS" -capture_cursor 1 -pixel_format uyvy422 -i "${SCREEN_DEV}:${MIC_DEV}" \
    -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p" \
    -c:v h264_videotoolbox -b:v 8M -r "$FPS" -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000 \
    -movflags +faststart "${dur[@]}" "$scr" >"$HERE/.record_screen.log" 2>&1 &
  local p1=$!
  ffmpeg -nostdin -hide_banner -loglevel warning \
    -f avfoundation -framerate "$FPS" -pixel_format uyvy422 -i "${CAM_DEV}:${MIC_DEV}" \
    -vf "format=yuv420p" -c:v h264_videotoolbox -b:v 8M -r "$FPS" -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000 \
    -movflags +faststart "${dur[@]}" "$cam" >"$HERE/.record_camera.log" 2>&1 &
  local p2=$!
  echo "$p1 $p2" > "$PIDFILE"
  sleep 3
  local dead=0
  kill -0 $p1 2>/dev/null || { echo "screen ffmpeg died:"; tail -3 "$HERE/.record_screen.log"; dead=1; }
  kill -0 $p2 2>/dev/null || { echo "camera ffmpeg died:"; tail -3 "$HERE/.record_camera.log"; dead=1; }
  if (( dead )); then kill -INT $p1 $p2 2>/dev/null; rm -f "$PIDFILE"; exit 2; fi
  echo "recording -> $scr + $cam (pids $p1 $p2). Stop with: $0 stop"
}

stop() {
  [[ -f "$PIDFILE" ]] || { echo "not recording"; exit 1; }
  local pids; pids=$(cat "$PIDFILE")
  for pid in $pids; do kill -INT "$pid" 2>/dev/null; done
  for i in {1..60}; do local alive=0; for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive=1; done; (( alive )) || break; sleep 0.25; done
  rm -f "$PIDFILE"
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
