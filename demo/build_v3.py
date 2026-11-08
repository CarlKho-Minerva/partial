import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np
T=os.path.expanduser("~/CODELocalProjects/partial/demo/takes"); W=os.path.expanduser("~/Movies/partial-demo-2026-11-07/v3/work"); OUT=os.path.expanduser("~/Movies/partial-demo-2026-11-07/v3/out")
os.makedirs(f"{W}/seg",exist_ok=True); os.makedirs(OUT,exist_ok=True)
def ff(*a): subprocess.run(["ffmpeg","-nostdin","-v","error","-y",*a],check=True)
def font(sz,bold=True):
    for p in [os.path.expanduser("~/Library/Fonts/Geist-Bold.ttf") if bold else os.path.expanduser("~/Library/Fonts/Geist-Medium.ttf"),"/System/Library/Fonts/Supplemental/Arial Bold.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return ImageFont.load_default()
LAG={ # seconds -> ms, measured by cross-correlation of the two mic tracks (xcorr2.py)
 "shot1":[(2.5,49.9),(7.5,-24.8),(12.5,-24.8),(17.5,-227.4),(22.5,-238.1),(27.5,-334.1),(32.5,-355.4),(37.5,-408.8),(42.5,-462.1),(47.5,-632.8),(52.5,-664.8),(57.5,-718.1),(62.5,-792.8),(67.5,-792.8),(72.5,-835.4),(77.5,-952.8),(82.5,-1080.8),(87.5,-1123.4),(92.5,-1304.8),(97.5,-1304.8),(102.5,-1336.8)],
 "shot2":[(2.5,101.2),(7.5,-58.8),(12.5,-80.1),(17.5,-165.4),(22.5,-261.4),(27.5,-261.4),(32.5,-368.1),(37.5,-453.4),(42.5,-453.4),(47.5,-485.4),(52.5,-517.4),(57.5,-570.8),(62.5,-613.4),(67.5,-730.8),(72.5,-741.4),(77.5,-741.4),(82.5,-709.4)],
 "shot3":[(2.5,63.0),(7.5,-33.0),(12.5,-161.0),(17.5,-182.3),(22.5,-289.0),(27.5,-310.3),(32.5,-438.3),(37.5,-502.3),(42.5,-513.0),(47.5,-545.0),(52.5,-673.0),(57.5,-747.7),(62.5,-843.7),(67.5,-918.3),(72.5,-1003.7),(77.5,-1067.7)],
 "shot6":[(2.5,70.9),(7.5,-78.4),(12.5,-78.4),(17.5,-163.8),(22.5,-185.1),(27.5,-195.8),(32.5,-270.4)]}
def lag(shot,t):
    xs=[a for a,b in LAG[shot]]; ys=[b for a,b in LAG[shot]]
    return float(np.interp(t,xs,ys))/1000.0   # window centre is t+3 s; tables are keyed by window start, so shift
def lagc(shot,t): return lag(shot,t-3.0)
FILES={s:(next(f for f in os.listdir(f"{T}/{s}") if f.startswith("screen")), next(f for f in os.listdir(f"{T}/{s}") if f.startswith("camera"))) for s in LAG}
# ---------- overlays (PNG, 1920x1080 RGBA) ----------
YEL=(250,204,60,255); WHITE=(255,255,255,255); GREEN=(80,220,120,255); GREY=(170,170,170,255); BLUE=(90,160,255,255)
def shadow_text(d,xy,txt,f,fill):
    x,y=xy; d.text((x+2,y+3),txt,font=f,fill=(0,0,0,170)); d.text((x,y),txt,font=f,fill=fill)
def label_png(name,items):
    im=Image.new("RGBA",(1920,1080),(0,0,0,0)); d=ImageDraw.Draw(im)
    for it in items:
        k=it[0]
        if k=="text": _,x,y,txt,sz,col=it; shadow_text(d,(x,y),txt,font(sz),col)
        elif k=="arrow":
            _,x0,y0,x1,y1,col=it; d.line((x0+2,y0+3,x1+2,y1+3),fill=(0,0,0,170),width=6); d.line((x0,y0,x1,y1),fill=col,width=5)
            v=np.array([x1-x0,y1-y0],float); v/=np.linalg.norm(v); p=np.array([-v[1],v[0]])
            tip=np.array([x1,y1]); a=tip-22*v+11*p; b=tip-22*v-11*p; d.polygon([tuple(tip),tuple(a),tuple(b)],fill=col)
    im.save(f"{W}/{name}.png")
label_png("ov_ch1",[("text",330,138,"ch1 = chin",34,WHITE),("arrow",330,160,262,206,WHITE)])
label_png("ov_clench",[("text",1060,338,"jaw clench",36,YEL),("arrow",1250,338,1392,262,YEL)])
files=["tape.bin","meta.json","events.csv  (cue log)","reads.csv  (read log)"]
for i in range(1,5): label_png(f"ov_files{i}",[("text",1480,840+44*j,"  "+files[j],30,WHITE if j<i-1 else YEL) for j in range(i)])
dmg=["metadata deleted","7 of 12 cue rows cut","read log deleted","33,345 bytes cut from the tape","40 bytes garbled"]
for i in range(1,6): label_png(f"ov_dmg{i}",[("text",1480,830+42*j,"  "+dmg[j],28,WHITE if j<i-1 else YEL) for j in range(i)])
def card(name,lines,bg=(18,18,17)):
    im=Image.new("RGB",(1920,1080),bg); d=ImageDraw.Draw(im); y=lines[0][3]
    for txt,sz,col,y in lines: 
        f=font(sz); w=d.textlength(txt,font=f); d.text(((1920-w)/2,y),txt,font=f,fill=col)
    im.save(f"{W}/{name}.png")
card("card_title",[("partial",120,(255,255,255),330),("reconstruct a damaged biosignal recording from its raw bytes",44,(255,255,255),490),("Carl Kho, Somach Systems  ·  AIE Code Summit 2026 Hackathon",34,(250,204,60),570)])
card("card_end",[("github.com/CarlKho-Minerva/partial",64,(255,255,255),400),("Carl Kho, Somach Systems, Inc.",36,(255,255,255),520),("AIE Code Summit 2026 Hackathon  ·  Meta Model API  ·  Software Archaeology",32,(250,204,60),590)])
im=Image.new("RGB",(1920,1080),(18,18,17)); d=ImageDraw.Draw(im)
d.text((160,120),"Real block, recorded on skin today",font=font(56),fill=(255,255,255)); d.text((160,196),"damaged copy given to the agent on Muse Spark 1.3, scored against the real driver",font=font(30,False),fill=(170,170,170))
rows=[("packets recovered","17,049 / 17,049",GREEN),("timestamps matched","yes",GREEN),("samples byte-identical","1.000",GREEN),("report written","no, ran out of steps",GREY),("total","0.23",GREY)]
for i,(k,v,c) in enumerate(rows):
    y=300+i*86; d.text((200,y),k,font=font(40,False),fill=(255,255,255)); d.text((1100,y),v,font=font(40),fill=c[:3])
    d.line((200,y+62,1720,y+62),fill=(50,50,50),width=2)
d.text((160,800),"The agent may not know. It may not make things up.",font=font(44),fill=(250,204,60))
im.save(f"{W}/card_score.png")
# ---------- segments ----------
def seg(shot,a,b,punch,overlays,name,full=False):
    scr,cam=(f"{T}/{shot}/{FILES[shot][0]}",f"{T}/{shot}/{FILES[shot][1]}")
    ca=a+lagc(shot,a); cb=b+lagc(shot,b); k=(b-a)/(cb-ca)
    inputs=["-ss",f"{a:.3f}","-to",f"{b:.3f}","-i",scr,"-ss",f"{ca:.3f}","-to",f"{cb:.3f}","-i",cam]
    for o in overlays: inputs+=["-i",f"{W}/{o[0]}.png"]
    if full:
        fc=f"[1:v]setpts=(PTS-STARTPTS)*{k:.6f},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:5,eq=brightness=-0.25[bg];[1:v]setpts=(PTS-STARTPTS)*{k:.6f},scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0,format=yuv420p[v]"
    else:
        z="scale=2036:1145,crop=1920:1080," if punch else ""
        fc=f"[0:v]setpts=PTS-STARTPTS,{z}format=yuv420p[scr];[1:v]setpts=(PTS-STARTPTS)*{k:.6f},crop=1080:1080:0:420,scale=360:360[cam];[scr][cam]overlay=24:696[v0]"
        cur="v0"
        for i,(png,t0,t1) in enumerate(overlays):
            fc+=f";[{cur}][{2+i}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{i+1}]"; cur=f"v{i+1}"
        fc+=f";[{cur}]format=yuv420p[v]"
    out=f"{W}/seg/{name}.mp4"
    ff(*inputs,"-filter_complex",fc,"-map","[v]","-map","0:a","-r","30","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-video_track_timescale","30000","-c:a","aac","-b:a","192k","-ar","48000","-ac","2","-t",f"{b-a:.3f}",out)
    print(f"{name}: screen {a:.2f}-{b:.2f} ({b-a:.1f}s) camera {ca:.2f}-{cb:.2f} lag {lagc(shot,a)*1000:+.0f}..{lagc(shot,b)*1000:+.0f} ms stretch {k:.4f}")
    return out,b-a
def cardclip(name,secs):
    out=f"{W}/seg/{name}.mp4"
    ff("-loop","1","-framerate","30","-t",f"{secs}","-i",f"{W}/{name}.png","-f","lavfi","-t",f"{secs}","-i","anullsrc=r=48000:cl=stereo","-r","30","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p","-video_track_timescale","30000","-c:a","aac","-b:a","192k","-shortest",out); return out,secs
plan=[]
plan.append(cardclip("card_title",2.0))
# shot1: final read 52.78 "Here's" ... 90.44 "still." + clench on screen to 93.9, cut pause, 96.68 "And" ... 104.70 "not."
a=52.43; plan.append(seg("shot1",a,86.36,False,[("ov_ch1",83.54-a,86.36-a)],"s1a"))
a=86.79; plan.append(seg("shot1",a,93.9,True,[("ov_ch1",0,1.2),("ov_clench",91.6-a,93.9-a)],"s1b"))
a=96.33; plan.append(seg("shot1",a,105.36,False,[],"s1c"))
a=68.91; plan.append(seg("shot2",a,87.54,True,[("ov_files1",72.64-a,73.34-a),("ov_files2",73.34-a,74.68-a),("ov_files3",74.68-a,78.20-a),("ov_files4",78.20-a,87.54-a)],"s2"))
a=54.43; plan.append(seg("shot3",a,81.42,False,[("ov_dmg1",61.26-a,62.56-a),("ov_dmg2",62.56-a,65.86-a),("ov_dmg3",65.86-a,69.86-a),("ov_dmg4",69.86-a,74.46-a),("ov_dmg5",74.46-a,81.42-a)],"s3"))
plan.append(cardclip("card_score",9.0))
a=12.11; plan.append(seg("shot6",a,22.14,False,[],"s6",full=True))
plan.append(cardclip("card_end",5.0))
with open(f"{W}/concat.txt","w") as f:
    for p,_ in plan: f.write(f"file '{p}'\n")
ff("-f","concat","-safe","0","-i",f"{W}/concat.txt","-c","copy",f"{OUT}/raw.mp4")
print("total planned", round(sum(d for _,d in plan),1))
