"""The reconstruction agent: a tool-calling loop on the Meta Model API, plus a scripted
stand-in (`fake_model=True`) so tests and the demo run with no key and no network."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .tools import SCHEMA, Tools

SYSTEM = """You are a software archaeologist. A recording session from a small biosignal board was damaged. The folder holds whatever survived: a raw serial capture (tape.bin), and maybe fragments of metadata, cue logs or host read logs. There is no driver, no datasheet, no source.

Your job is to recover the session from the bytes, and to be honest about which parts you saw and which parts you guessed.

Work in this order:
1. Inventory the folder (ls). Read every text file that survived. Treat notes as weak claims; the bytes are the strong claims.
2. Reverse the wire format from tape.bin: byte_histogram and find_bytes to locate sync markers and the packet period; hexdump to read a few packets by eye; work out the packet length, where the timestamp is, its width and endianness, how many channels there are, how wide each sample is, and whether there is a checksum and how it is computed. Verify every hypothesis against the bytes (a checksum rule must hold on hundreds of packets, not three).
3. Write parse_tape.py that walks the whole tape, resynchronises after damage, skips packets that fail the checksum, and saves parsed_agent.npz with two arrays: board_ms (uint32, one per packet) and counts (int32, packets x channels). Run it. Fix it until it runs clean and prints the packet count, the recovered sample rate (from the timestamp steps), per-channel rms, and how many bytes were skipped.
4. Decide which channels carry a real signal (quiet, microvolt-scale noise with bursts) versus floating inputs (huge slow drift). Map any cue rows you have onto packet indices using the timestamps you can actually relate. If reads.csv survived, use it to relate host time to board time; if not, say the mapping is inferred.
5. Write make_figures.py (numpy and matplotlib only) that saves figures/overview.png: every channel over time with cue onsets as vertical lines, unusable channels greyed. Run it.
6. Write reconstruction.json. EVERY claim is an object {"value": ..., "status": "observed" | "inferred", "evidence": "<what in the bytes or files supports it>", "confidence": 0..1}. Use "observed" only for things you verified against the data in this folder. Shape:
{
 "wire_format": {"packet_length": claim, "start_marker": claim, "end_marker": claim, "timestamp": claim, "n_channels": claim, "sample_encoding": claim, "checksum": claim},
 "sample_rate_hz": claim, "lsb_volts": claim, "packets_recovered": claim, "bytes_skipped": claim,
 "usable_channels": claim (value is a list of 1-based channel numbers),
 "trials": [{"trial": int, "label": claim, "sample": claim}],
 "what_is_missing": ["..."],
 "summary": "five plain sentences"
}
Never invent a trial label you cannot ground in a surviving file; if a label is unknown, give value null with status "inferred" and say why. If volts-per-count cannot be derived from the data, say so and give your best inference with low confidence.
Stop when parsed_agent.npz, figures/overview.png and reconstruction.json all exist."""


@dataclass
class RunLog:
    steps: list[dict] = field(default_factory=list)
    model: str = ""
    elapsed_s: float = 0.0
    stopped: str = ""


# ---------------------------------------------------------------------------
# The scripted stand-in. It plays the role of the model: the same tool calls a good run
# makes, in order, ending with the same three artefacts. It is not a parser hidden in the
# agent; it is a fixed transcript so the loop, the tools and the scorer can be tested.
# ---------------------------------------------------------------------------

FAKE_PARSER = r'''
import json, struct, sys
import numpy as np
raw = open("tape.bin", "rb").read()
START, END, L = b"\xab\xcd", b"\xdc\xba", 37
pos, n = 0, len(raw)
ts, rows, bad, skipped = [], [], 0, 0
while True:
    s = raw.find(START, pos)
    if s < 0 or n - s < L:
        skipped += (n - pos) if s < 0 else (s - pos)
        break
    skipped += s - pos
    p = raw[s:s + L]
    if p[2] != 31 or p[35:37] != END or (sum(p[2:34]) & 0xFF) != p[34]:
        bad += p[2] == 31 and p[35:37] == END
        skipped += 1
        pos = s + 1
        continue
    ts.append(struct.unpack(">I", p[3:7])[0])
    rows.append([int.from_bytes(p[10 + 3 * c:13 + 3 * c], "big", signed=True) for c in range(8)])
    pos = s + L
board_ms = np.array(ts, np.uint32)
counts = np.array(rows, np.int32)
np.savez_compressed("parsed_agent.npz", board_ms=board_ms, counts=counts)
d = np.diff(board_ms.astype(np.int64))
step = float(np.median(d)) if d.size else float("nan")
rms = np.sqrt(np.mean(counts.astype(np.float64) ** 2, axis=0)) if counts.size else []
print(json.dumps({"packets": int(board_ms.size), "median_step_ms": step,
                  "fs_hz": 1000.0 / step if step else None, "checksum_failures": int(bad),
                  "skipped_bytes": int(skipped), "rms_counts": [round(float(x)) for x in rms],
                  "backwards_steps": int((d < 0).sum()) if d.size else 0}))
'''

FAKE_FIGURES = r'''
import csv, json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
z = np.load("parsed_agent.npz")
t = (z["board_ms"].astype(np.int64) - int(z["board_ms"][0])) / 1000.0
c = z["counts"].astype(np.float64)
rec = json.load(open("reconstruction.json")) if os.path.exists("reconstruction.json") else {}
usable = set(rec.get("usable_channels", {}).get("value", []) or [])
fig, axes = plt.subplots(c.shape[1], 1, figsize=(12, 1.2 * c.shape[1]), sharex=True)
for i, ax in enumerate(axes):
    ax.plot(t, c[:, i], lw=0.4, color=("tab:blue" if (i + 1) in usable else "0.7"))
    ax.set_ylabel(f"ch{i + 1}", rotation=0, labelpad=18)
for tr in rec.get("trials", []):
    s = tr.get("sample", {}).get("value")
    if s is not None and 0 <= s < t.size:
        for ax in axes:
            ax.axvline(t[s], color="tab:red", lw=0.6)
axes[-1].set_xlabel("seconds since first packet")
fig.suptitle("recovered channels; red = cue onsets; grey = judged unusable")
os.makedirs("figures", exist_ok=True)
fig.savefig("figures/overview.png", dpi=110, bbox_inches="tight")
print("wrote figures/overview.png")
'''


def _claim(value, status, evidence, confidence):
    return {"value": value, "status": status, "evidence": evidence, "confidence": confidence}


class FakeModel:
    """Yields tool calls like the real loop would, then a final message. After the listing
    it fixes a plan; results it needs (events, meta, the parser's output) are captured."""

    def __init__(self):
        self.queue: list[tuple[str, dict]] = [("ls", {})]
        self.started = False
        self.parse_out: dict = {}
        self.events: list[dict] = []
        self.meta: dict | None = None
        self.reads_present = False
        self.n_events_total: int | None = None

    def next(self, last_tool: str | None, last_result: str) -> tuple[str | None, dict | None, str | None]:
        if last_tool == "ls" and not self.started:
            self.started = True
            self.reads_present = "reads.csv" in last_result
            self.queue += [("byte_histogram", {"path": "tape.bin"}),
                           ("find_bytes", {"path": "tape.bin", "hex": "ABCD"}),
                           ("hexdump", {"path": "tape.bin", "offset": 0, "length": 148})]
            if "events.csv" in last_result:
                self.queue.append(("read_text", {"path": "events.csv"}))
            if "meta.json" in last_result:
                self.queue.append(("read_text", {"path": "meta.json"}))
            self.queue += [("write_file", {"path": "parse_tape.py", "content": FAKE_PARSER}),
                           ("run_python", {"path": "parse_tape.py"}),
                           ("write_file", {"path": "reconstruction.json", "content": ""}),
                           ("write_file", {"path": "make_figures.py", "content": FAKE_FIGURES}),
                           ("run_python", {"path": "make_figures.py"})]
        elif last_tool == "read_text":
            if last_result.lstrip().startswith("{"):
                try:
                    self.meta = json.loads(last_result)
                    self.n_events_total = self.meta.get("n_events")
                except json.JSONDecodeError:
                    self.meta = None
            else:
                self.events = _parse_events(last_result)
        elif last_tool == "run_python" and "parsed_agent" not in last_result and "wrote figures" not in last_result:
            self.parse_out = _last_json(last_result)
        if not self.queue:
            return None, None, "Reconstruction written: parsed_agent.npz, reconstruction.json, figures/overview.png."
        name, args = self.queue.pop(0)
        if name == "write_file" and args["path"] == "reconstruction.json":
            args = {"path": "reconstruction.json", "content": json.dumps(self._reconstruction(), indent=1)}
        return name, args, None

    def _reconstruction(self) -> dict:
        po = self.parse_out
        fs = po.get("fs_hz")
        rms = po.get("rms_counts", [])
        usable = [i + 1 for i, r in enumerate(rms) if 0 < r < 2000]
        gain_known = bool(self.meta and self.meta.get("gain"))
        trials = []
        for ev in self.events:
            trials.append({"trial": ev["trial"],
                           "label": _claim(ev["label"], "observed", "row in surviving events.csv", 0.95),
                           "sample": _claim(ev.get("sample"), "observed" if self.reads_present else "inferred",
                                            "events.csv sample column" + ("" if self.reads_present else "; reads.csv missing, host-to-board mapping not re-derivable"),
                                            0.9 if self.reads_present else 0.5)})
        n_total = self.n_events_total
        if n_total and len(trials) < n_total:
            for k in range(len(trials), n_total):
                trials.append({"trial": k, "label": _claim(None, "inferred", "events.csv truncated; no surviving source for this label", 0.0),
                               "sample": _claim(None, "inferred", "no cue row survived", 0.0)})
        missing = []
        if not self.meta:
            missing.append("meta.json (gain, montage, sites)")
        if not self.reads_present:
            missing.append("reads.csv (host clock to board clock map)")
        if n_total and len(self.events) < n_total:
            missing.append(f"{n_total - len(self.events)} trial rows of events.csv")
        return {
            "wire_format": {
                "packet_length": _claim(37, "observed", "AB CD sync markers repeat every 37 bytes in find_bytes gap histogram", 0.98),
                "start_marker": _claim("ABCD", "observed", "most common 2-byte pair, fixed spacing", 0.98),
                "end_marker": _claim("DCBA", "observed", "last two bytes before every next ABCD", 0.97),
                "timestamp": _claim("u32 big-endian ms at bytes 3..6", "observed", "increments by 4 per packet", 0.95),
                "n_channels": _claim(8, "observed", "27 payload bytes after 3 status bytes = 8 x 3", 0.9),
                "sample_encoding": _claim("int24 big-endian, two's complement", "observed", "values centred near zero on quiet channels when signed", 0.85),
                "checksum": _claim("sum(bytes[2:34]) & 0xFF at byte 34", "observed", f"holds on {po.get('packets', 0)} packets, fails on {po.get('checksum_failures', 0)}", 0.95),
            },
            "sample_rate_hz": _claim(round(fs, 3) if fs else None, "observed", f"median timestamp step {po.get('median_step_ms')} ms", 0.95),
            "lsb_volts": _claim((2 * 4.5 / self.meta["gain"]) / 2**24 if gain_known else 2.235e-8, "observed" if gain_known else "inferred",
                                "gain in surviving meta.json, ADS1299 formula" if gain_known else "no gain survived; assumed ADS1299 at gain 24, Vref 4.5 V", 0.9 if gain_known else 0.4),
            "packets_recovered": _claim(po.get("packets"), "observed", "parse_tape.py output", 1.0),
            "bytes_skipped": _claim(po.get("skipped_bytes"), "observed", "parse_tape.py output", 1.0),
            "usable_channels": _claim(usable, "inferred", "rms under 2000 counts and no slow drift; others look like floating inputs", 0.7),
            "trials": trials,
            "what_is_missing": missing,
            "summary": ("The tape is a stream of 37-byte packets with a 32-bit millisecond clock and eight 24-bit samples. "
                        f"{po.get('packets')} packets survived the damage; the parser resynchronised after {po.get('skipped_bytes')} skipped bytes. "
                        f"The clock steps 4 ms, so the board ran at about {round(fs or 0)} samples per second. "
                        f"Channels {usable} carry a real signal. "
                        "Labels come only from the surviving cue rows; nothing was invented for the missing ones."),
        }


def _parse_events(text: str) -> list[dict]:
    import csv
    import io
    rows = []
    try:
        for r in csv.DictReader(io.StringIO(text.split("\n...[truncated]")[0])):
            try:
                rows.append({"trial": int(r["trial"]), "label": r["label"],
                             "sample": int(r["sample"]) if r.get("sample") not in (None, "", "-1") else None})
            except (KeyError, ValueError):
                continue
    except Exception:  # noqa: BLE001
        pass
    return rows


def _last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def reconstruct(session: Path, max_steps: int = 40, model: str | None = None,
                fake_model: bool | None = None, verbose: bool = True) -> RunLog:
    if fake_model is None:
        fake_model = os.environ.get("PARTIAL_FAKE_MODEL") == "1"
    tools = Tools(session)
    log = RunLog(model="fake" if fake_model else (model or os.environ.get("PARTIAL_MODEL", "muse-spark-1.3")))
    t0 = time.time()
    logf = open(session / "agent_log.jsonl", "w")

    def record(kind, **kw):
        row = {"t": round(time.time() - t0, 3), "kind": kind, **kw}
        log.steps.append(row)
        logf.write(json.dumps(row) + "\n")
        logf.flush()

    if fake_model:
        fm = FakeModel()
        last_tool, last_result = None, ""
        for _ in range(max_steps):
            name, args, final = fm.next(last_tool, last_result)
            if name is None:
                record("final", text=final)
                log.stopped = "final"
                break
            out = tools.dispatch(name, args)
            record("tool", name=name, args=args, result=out[:400])
            if verbose:
                print(f"[{name}] {out[:160].replace(chr(10), ' ')}")
            last_tool, last_result = name, out
        else:
            log.stopped = "max_steps"
    else:
        from .meta_client import chat
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Session folder: {session.name}. Begin with ls."}]
        log.stopped = "max_steps"
        for _ in range(max_steps):
            r = chat(messages, SCHEMA, model=log.model)
            m = r.choices[0].message
            messages.append({"role": "assistant", "content": m.content or "",
                             **({"tool_calls": [tc.model_dump() for tc in m.tool_calls]} if m.tool_calls else {})})
            if not m.tool_calls:
                record("final", text=m.content or "")
                log.stopped = "final"
                break
            for tc in m.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = tools.dispatch(tc.function.name, args)
                record("tool", name=tc.function.name, args=args, result=out[:400])
                if verbose:
                    print(f"[{tc.function.name}] {out[:160].replace(chr(10), ' ')}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})
    log.elapsed_s = round(time.time() - t0, 2)
    logf.close()
    return log
