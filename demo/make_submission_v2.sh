#!/bin/zsh
set -e
T=~/CODELocalProjects/partial/demo/takes; W=work; C=cards
ENC=(-c:v h264_videotoolbox -b:v 10M -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000)
i=0
# seg NAME SCREEN CAMERA START END CAMOFF PUNCH LABELS(filter snippet using [v1] -> [v2])
seg() { local scr=$1 cam=$2 a=$3 b=$4 off=$5 punch=$6 labels=$7; i=$((i+1)); local out=$(printf "$W/seg%02d.mp4" $i)
  local ca=$(python3 -c "print(max(0,$a+($off)))") cb=$(python3 -c "print($b+($off))")
  local pz="null"; [[ $punch == 1 ]] && pz="scale=2035:1145,crop=1920:1080"
  ffmpeg -nostdin -v error -y -ss $a -to $b -i "$scr" -ss $ca -to $cb -i "$cam" -i $C/l_ch1.png -i $C/l_clench.png -i $C/l_file0.png -i $C/l_file1.png -i $C/l_file2.png -i $C/l_file3.png -i $C/l_dmg0.png -i $C/l_dmg1.png -i $C/l_dmg2.png -i $C/l_dmg3.png -i $C/l_dmg4.png \
    -filter_complex "[0:v]$pz,format=yuv420p[scr];[1:v]scale=420:-2,format=yuva420p[cam];[scr][cam]overlay=28:H-h-28[v1];${labels}" -map "[v]" -map 0:a -t $(python3 -c "print($b-$a)") "${ENC[@]}" "$out"; echo "$out $a-$b"; }
S1=$T/shot1/screen-20261107-161048.mp4; C1=$T/shot1/camera-20261107-161048.mp4
S2=$T/shot2/screen-20261107-161304.mp4; C2=$T/shot2/camera-20261107-161304.mp4
S3=$T/shot3/screen-20261107-161453.mp4; C3=$T/shot3/camera-20261107-161453.mp4
S6=$T/shot6/screen-20261107-161646.mp4; C6=$T/shot6/camera-20261107-161646.mp4
NOL="[v1]format=yuv420p[v]"
# title
ffmpeg -nostdin -v error -y -loop 1 -t 2 -i $C/title.png -f lavfi -t 2 -i "anullsrc=r=48000:cl=stereo" -vf format=yuv420p "${ENC[@]}" $W/seg00.mp4
# shot 1
seg $S1 $C1 44.6 86.95 0 0 "$NOL"
seg $S1 $C1 87.5 94.75 0 1 "[v1][2:v]overlay=1180:160:enable='between(t,0.6,7.2)',format=yuv420p[v]"
seg $S1 $C1 95.75 100.85 0 0 "[v1][3:v]overlay=1180:160:enable='between(t,0.8,5.1)',format=yuv420p[v]"
seg $S1 $C1 102.3 106.9 0 1 "$NOL"
# shot 2
seg $S2 $C2 75.3 77.5 0 0 "$NOL"
seg $S2 $C2 78.8 87.2 0 1 "[v1][4:v]overlay=1200:120:enable='gte(t,0.3)'[v1b];[v1b][5:v]overlay=1200:200:enable='gte(t,1.4)'[v1c];[v1c][6:v]overlay=1200:280:enable='gte(t,2.6)'[v1d];[v1d][7:v]overlay=1200:360:enable='gte(t,5.0)',format=yuv420p[v]"
seg $S2 $C2 87.8 98.0 0 0 "$NOL"
# shot 3
seg $S3 $C3 62.2 81.9 0 1 "[v1][8:v]overlay=1200:120:enable='gte(t,4.0)'[a1];[a1][9:v]overlay=1200:200:enable='gte(t,6.3)'[a2];[a2][10:v]overlay=1200:280:enable='gte(t,8.6)'[a3];[a3][11:v]overlay=1200:360:enable='gte(t,11.2)'[a4];[a4][12:v]overlay=1200:440:enable='gte(t,15.6)',format=yuv420p[v]"
seg $S3 $C3 82.6 89.5 0 0 "$NOL"
# score card 10 s
ffmpeg -nostdin -v error -y -loop 1 -t 10 -i $C/score.png -f lavfi -t 10 -i "anullsrc=r=48000:cl=stereo" -vf format=yuv420p "${ENC[@]}" $W/seg50.mp4
# shot 6: camera full frame, letterboxed on blurred fill, screen audio, cam offset -0.16
for r in "27.0 28.4" "29.2 41.2"; do read a6 b6 <<< "$r"; set -- $a6 $b6; i=$((i+1)); out=$(printf "$W/seg%02d.mp4" $((50+i)))
  ca=$(python3 -c "print($1-0.16)"); cb=$(python3 -c "print($2-0.16)")
  ffmpeg -nostdin -v error -y -ss $ca -to $cb -i "$C6" -ss $1 -to $2 -i "$S6" -filter_complex "[0:v]split[a][b];[a]scale=1920:1080,boxblur=40:8,setsar=1[bg];[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,format=yuv420p[v]" -map "[v]" -map 1:a -t $(python3 -c "print($2-$1)") "${ENC[@]}" "$out"; echo "$out shot6 $1-$2"; done
ffmpeg -nostdin -v error -y -loop 1 -t 5 -i $C/end.png -f lavfi -t 5 -i "anullsrc=r=48000:cl=stereo" -vf format=yuv420p "${ENC[@]}" $W/seg99.mp4
ls $W/seg*.mp4 | sort | sed "s|^|file '|; s|$|'|" > $W/list.txt
ffmpeg -nostdin -v error -y -f concat -safe 0 -i $W/list.txt -c copy $W/concat.mp4
# two-pass loudnorm
J=$(ffmpeg -nostdin -i $W/concat.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
I=$(echo "$J" | python3 -c "import sys,json;d=json.load(sys.stdin);print(f\"measured_I={d['input_i']}:measured_TP={d['input_tp']}:measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d['target_offset']}\")")
ffmpeg -nostdin -v error -y -i $W/concat.mp4 -c:v copy -af "loudnorm=I=-16:TP=-1.5:LRA=11:$I:linear=true" -c:a aac -b:a 192k -ar 48000 -movflags +faststart out/partial-submission-v2.mp4
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate -show_entries format=duration -of compact out/partial-submission-v2.mp4
