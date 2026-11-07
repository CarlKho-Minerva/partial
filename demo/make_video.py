"""Render the 1-minute demo as PNG frames with PIL, then ffmpeg joins them. No em dashes."""
import json, subprocess, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
OUT = Path("demo/frames"); OUT.mkdir(parents=True, exist_ok=True)
MONO = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 30)
MONO_S = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 26)
SANS = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 56)
SANS_S = ImageFont.truetype("/System/Library/Fonts/SFNS.ttf", 34)
BG, FG, DIM, ACC = (12, 12, 14), (236, 236, 236), (140, 140, 140), (255, 200, 60)
frames = []

def frame(img): 
    p = OUT / f"f{len(frames):05d}.png"; img.save(p); frames.append(p)

def hold(img, secs):
    for _ in range(int(secs * FPS)): frame(img)

def caption_slide(text, sub=None):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    lines = textwrap.wrap(text, 42)
    y = H // 2 - 40 * len(lines)
    for ln in lines:
        w = d.textlength(ln, font=SANS); d.text(((W - w) / 2, y), ln, font=SANS, fill=FG); y += 76
    if sub:
        w = d.textlength(sub, font=SANS_S); d.text(((W - w) / 2, y + 30), sub, font=SANS_S, fill=DIM)
    return im

def term_slide(lines, caption, hi=None):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle((60, 40, W - 60, 110), fill=(24, 24, 28))
    d.text((90, 56), caption, font=SANS_S, fill=ACC)
    y = 140
    for ln in lines[-26:]:
        col = FG
        if ln.startswith("$ "): col = ACC
        elif "TOTAL" in ln: col = ACC
        elif " 0.00" in ln or " 0.38" in ln: col = (255, 120, 120)
        d.text((90, y), ln[:118], font=MONO_S, fill=col); y += 34
    return im

# 1. title
hold(caption_slide("partial: reconstruct a damaged biosignal tape from its raw bytes",
                   "a coding agent on Meta Model API, scored against a held-out oracle"), 4)

# 2. terminal: the fake-model run typed line by line
log = Path("demo/fake_run.log").read_text().splitlines()
log = [l for l in log if not l.startswith("partial demo")]
shown = ["$ partial demo --fake-model"]
hold(term_slide(shown, "damage: metadata deleted, cue log cut, 21,737 bytes removed, 40 garbled"), 0.8)
for l in log:
    shown.append(l)
    cap = "damage: metadata deleted, cue log cut, 21,737 bytes removed, 40 garbled"
    if "reconstruction of" in l or shown.index(l) > 8:
        cap = "the agent writes its own parser and labels every claim observed or inferred"
    hold(term_slide(shown, cap), 0.45 if "damage" in l or "synth" in l or "agent:" in l else 0.5)
hold(term_slide(shown, "the agent writes its own parser and labels every claim observed or inferred"), 2.5)

# 3. figure
fig = Image.open("examples/overview-fake-model.png").convert("RGB")
fig.thumbnail((W - 160, H - 220))
im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
d.rectangle((60, 40, W - 60, 110), fill=(24, 24, 28))
d.text((90, 56), "the figure the agent produced: channels 5 to 8 greyed as floating, the cut at 32 s", font=SANS_S, fill=ACC)
im.paste(fig, ((W - fig.width) // 2, 140))
hold(im, 5)

# 4. the live Muse table
muse = Path("examples/muse-run-2026-11-07/demo.log").read_text().splitlines()
start = next(i for i, l in enumerate(muse) if l.startswith("agent:"))
tbl = ["$ partial demo   # live, muse-spark-1.3"] + muse[start:start + 19]
tbl = [l for l in tbl if not l.startswith("partial demo")]
hold(term_slide(tbl, "scored against a held-out oracle: samples byte-identical, 0.88 on Muse Spark 1.3"), 9)

# 5. reconstruction.json excerpt
ex = json.dumps({"packet_length": {"value": 37, "status": "observed",
      "evidence": "AB CD sync markers repeat every 37 bytes", "confidence": 0.98},
     "volts_per_count": {"value": None, "status": "inferred",
      "evidence": "no gain register readable from the tape; not guessed", "confidence": 0.0}}, indent=2).splitlines()
hold(term_slide(ex, "every claim carries value, observed or inferred, evidence, confidence"), 5)

# 6. close
hold(caption_slide("AIE Code Summit 2026 · Software Archaeology · Meta Model API",
                   "github.com/CarlKho-Minerva/partial · Carl Kho, Somach Systems, Inc."), 5)

print("frames", len(frames), "seconds", len(frames) / FPS)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(OUT / "f%05d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", "demo/partial-demo.mp4"], check=True)
print("wrote demo/partial-demo.mp4")
