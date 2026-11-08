#!/bin/zsh
# make_submission.sh: cut the hackathon submission video from the live takes (2026-11-07).
# Shots are screen + Rode mic with the camera as a portrait picture-in-picture; shot 6 is camera only.
set -eu
cd "$(dirname "$0")"
FONT=/System/Library/Fonts/Helvetica.ttc
W=/tmp/partial_cut; mkdir -p $W; setopt +o nomatch; rm -f $W/0*.mp4 $W/list.txt
ENC=(-c:v libx264 -preset veryfast -crf 20 -r 30 -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000)
S1=$(ls takes/shot1/screen-*.mp4); C1=$(ls takes/shot1/camera-*.mp4)
S2=$(ls takes/shot2/screen-*.mp4); C2=$(ls takes/shot2/camera-*.mp4)
S3=$(ls takes/shot3/screen-*.mp4); C3=$(ls takes/shot3/camera-*.mp4)
C6=$(ls takes/shot6/camera-*.mp4); S6=$(ls takes/shot6/screen-*.mp4)
PIP="[1:v]scale=480:-2,format=yuv420p[cam];[0:v]format=yuv420p[scr];[scr][cam]overlay=24:H-h-24[v]"
# a screen+pip segment: $1 out, $2 screen, $3 camera, $4 start, $5 end
seg() { ffmpeg -v error -y -ss "$4" -to "$5" -i "$2" -ss "$4" -to "$5" -i "$3" -filter_complex "$PIP" -map "[v]" -map 0:a "${ENC[@]}" "$1"; }
# title card
# cards are PNGs rendered by PIL (this ffmpeg has no drawtext); see the python block in git history
ffmpeg -v error -y -loop 1 -t 2.5 -i $W/title.png -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 2.5 -vf format=yuv420p "${ENC[@]}" $W/00_title.mp4
seg $W/01_shot1a.mp4 "$S1" "$C1" 51.3 91.5
seg $W/02_shot1b.mp4 "$S1" "$C1" 95.5 105.4
seg $W/03_shot2.mp4  "$S2" "$C2" 60.0 87.6
seg $W/04_shot3.mp4  "$S3" "$C3" 54.8 81.4
# the score table from the earlier render, with the honest real-block caption
ffmpeg -v error -y -ss 31.2 -to 43.2 -i partial-demo.mp4 -f lavfi -i "anullsrc=r=48000:cl=stereo" \
  -i $W/caption.png -filter_complex "[0:v][2:v]overlay=0:0,format=yuv420p[v]" \
  -map "[v]" -map 1:a -shortest "${ENC[@]}" $W/05_score.mp4
# shot 6: camera full frame, portrait centred on dark
ffmpeg -v error -y -ss 26.4 -to 43.2 -i "$C6" -ss 26.4 -to 43.2 -i "$S6" -filter_complex "[0:v]scale=-2:1080,pad=1920:1080:(ow-iw)/2:0:color=0x1a1a19,format=yuv420p[v]" -map "[v]" -map 1:a "${ENC[@]}" $W/06_shot6.mp4
ffmpeg -v error -y -loop 1 -t 2.5 -i $W/end.png -f lavfi -i "anullsrc=r=48000:cl=stereo" -t 2.5 -vf format=yuv420p "${ENC[@]}" $W/07_end.mp4
for f in $W/0*.mp4; do echo "file '$f'"; done > $W/list.txt
ffmpeg -v error -y -f concat -safe 0 -i $W/list.txt -af "loudnorm=I=-16:TP=-1.5:LRA=11" "${ENC[@]}" partial-submission.mp4
ffprobe -v error -show_entries format=duration,size -of default=nw=1 partial-submission.mp4
