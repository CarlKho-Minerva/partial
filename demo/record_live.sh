#!/bin/zsh
# record_live.sh start | stop | status
# Screen of the Mac 48 + FaceTime camera as a picture-in-picture (bottom-left, a quarter wide) + microphone.
# Output: demo/live-<stamp>.mp4, 1920x1080, 30 fps, H.264 + AAC.
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
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already recording (pid $(cat "$PIDFILE")); run: $0 stop"; exit 1
  fi
  local stamp out
  stamp=$(date +%Y%m%d-%H%M%S); out="$HERE/live-$stamp.mp4"
  local secs="${1:-}"; local dur=()
  [[ -n "$secs" ]] && dur=(-t "$secs")
  # screen (video) + mic (audio) as one avfoundation input, camera as a second input
  ffmpeg -nostdin -hide_banner -loglevel warning \
    -f avfoundation -framerate "$FPS" -capture_cursor 1 -pixel_format uyvy422 -i "${SCREEN_DEV}:${MIC_DEV}" \
    -f avfoundation -framerate "$FPS" -pixel_format uyvy422 -i "${CAM_DEV}:none" \
    -filter_complex "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[scr];[1:v]scale=${PIP_W}:-2,format=yuv420p[cam];[scr][cam]overlay=${PAD}:H-h-${PAD}:format=auto[v]" \
    -map "[v]" -map 0:a -c:v h264_videotoolbox -b:v 8M -r "$FPS" -pix_fmt yuv420p \
    -c:a aac -b:a 160k -ar 48000 -movflags +faststart "${dur[@]}" "$out" \
    >"$HERE/.record_live.log" 2>&1 &
  echo $! > "$PIDFILE"
  sleep 2
  if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "ffmpeg died at start; last lines of the log:"; tail -5 "$HERE/.record_live.log"; rm -f "$PIDFILE"; exit 2
  fi
  echo "recording -> $out (pid $(cat "$PIDFILE")). Stop with: $0 stop"
}

stop() {
  [[ -f "$PIDFILE" ]] || { echo "not recording"; exit 1; }
  local pid; pid=$(cat "$PIDFILE")
  kill -INT "$pid" 2>/dev/null || { echo "pid $pid not running"; rm -f "$PIDFILE"; exit 1; }
  for i in {1..40}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
  rm -f "$PIDFILE"
  local out; out=$(ls -t "$HERE"/live-*.mp4 2>/dev/null | head -1)
  echo "stopped. file: $out"
  ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate -show_entries format=duration -of default=nw=1 "$out" 2>/dev/null
}

status() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then echo "recording (pid $(cat "$PIDFILE"))"; else echo "idle"; fi
}

case "${1:-}" in
  start) start "${2:-}" ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 start [seconds] | stop | status"; exit 64 ;;
esac
