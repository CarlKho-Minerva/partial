"""Agent tools. Every path is resolved inside one session directory and refused otherwise."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

MAX_TEXT = 20000
MAX_HEX = 2048
RUN_TIMEOUT_S = 120

SCHEMA = [
    {"type": "function", "function": {"name": "ls", "description": "List every file in the session folder with its size in bytes.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {"name": "read_text", "description": "Read a text, csv, json or jsonl file (first 20000 characters).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "hexdump", "description": "Hex dump of a binary file: offset, 16 bytes per line, ASCII column. length is capped at 2048 bytes.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "length": {"type": "integer"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "byte_histogram", "description": "Byte-value histogram of a binary file (top 24 values) and the 12 most common 2-byte sequences with their mean spacing. Good for finding sync markers and the packet period.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "find_bytes", "description": "Offsets of a hex byte pattern (e.g. 'ABCD') in a binary file: count, first 20 offsets, and the histogram of gaps between consecutive hits.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "hex": {"type": "string"}}, "required": ["path", "hex"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write a file inside the session folder (e.g. parse_tape.py, reconstruction.json).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "run_python", "description": "Run a python script that lives in the session folder, with the folder as cwd. numpy and matplotlib are available. Returns stdout and stderr (last 6000 chars).",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "np_summary", "description": "Shape, dtype, per-column mean, std, rms, flatline flags and NaN count of a .npy or .npz file in the session folder.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
]


class Tools:
    def __init__(self, session: Path):
        self.root = session.resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"session folder not found: {self.root}")

    def _p(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"path escapes the session folder: {path}")
        return p

    def ls(self) -> str:
        rows = [f"{p.relative_to(self.root)}  {p.stat().st_size} bytes"
                for p in sorted(self.root.rglob("*")) if p.is_file()]
        return "\n".join(rows) or "(empty)"

    def read_text(self, path: str) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        s = p.read_text(errors="replace")
        return s[:MAX_TEXT] + ("\n...[truncated]" if len(s) > MAX_TEXT else "")

    def hexdump(self, path: str, offset: int = 0, length: int = 256) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        length = max(1, min(int(length), MAX_HEX))
        offset = max(0, int(offset))
        with open(p, "rb") as fh:
            fh.seek(offset)
            b = fh.read(length)
        out = [f"file size {p.stat().st_size} bytes; showing {len(b)} from offset {offset}"]
        for i in range(0, len(b), 16):
            chunk = b[i:i + 16]
            hx = " ".join(f"{x:02X}" for x in chunk)
            asc = "".join(chr(x) if 32 <= x < 127 else "." for x in chunk)
            out.append(f"{offset + i:08X}  {hx:<47}  {asc}")
        return "\n".join(out)

    def byte_histogram(self, path: str) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        b = np.frombuffer(p.read_bytes(), dtype=np.uint8)
        if b.size == 0:
            return "empty file"
        counts = np.bincount(b, minlength=256)
        top = sorted(range(256), key=lambda v: -counts[v])[:24]
        pairs = b[:-1].astype(np.uint16) * 256 + b[1:]
        pc = np.bincount(pairs, minlength=65536)
        top_pairs = np.argsort(-pc)[:12]
        rows = []
        for v in top_pairs:
            hits = np.flatnonzero(pairs == v)
            gap = float(np.median(np.diff(hits))) if hits.size > 1 else float("nan")
            rows.append({"pair": f"{v >> 8:02X}{v & 0xFF:02X}", "count": int(pc[v]), "median_gap": gap})
        return json.dumps({"size": int(b.size),
                           "top_bytes": [{"byte": f"{v:02X}", "count": int(counts[v])} for v in top],
                           "top_pairs": rows})

    def find_bytes(self, path: str, hex: str) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        try:
            pat = bytes.fromhex(hex.replace(" ", ""))
        except ValueError:
            return f"ERROR: bad hex {hex!r}"
        if not pat:
            return "ERROR: empty pattern"
        raw = p.read_bytes()
        hits = []
        i = raw.find(pat)
        while i >= 0 and len(hits) < 200000:
            hits.append(i)
            i = raw.find(pat, i + 1)
        gaps = Counter(np.diff(np.array(hits)).tolist()) if len(hits) > 1 else Counter()
        return json.dumps({"pattern": pat.hex().upper(), "count": len(hits), "first": hits[:20],
                           "gap_histogram": dict(sorted(gaps.items(), key=lambda kv: -kv[1])[:10])})

    def write_file(self, path: str, content: str) -> str:
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return f"wrote {p.relative_to(self.root)} ({len(content)} chars)"

    def run_python(self, path: str) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        try:
            r = subprocess.run([sys.executable, "-I", str(p)], cwd=self.root, capture_output=True,
                               text=True, timeout=RUN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return f"ERROR: timed out after {RUN_TIMEOUT_S}s"
        out = (r.stdout + r.stderr)[-6000:]
        return f"exit {r.returncode}\n{out or '(no output)'}"

    def np_summary(self, path: str) -> str:
        p = self._p(path)
        if not p.is_file():
            return f"ERROR: no such file {path}"
        try:
            loaded = np.load(p, allow_pickle=False)
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {e}"
        arrays = {k: loaded[k] for k in loaded.files} if hasattr(loaded, "files") else {"array": loaded}
        out = {}
        for k, a in arrays.items():
            a = np.asarray(a)
            if a.ndim == 1:
                a = a[:, None]
            af = a.astype(np.float64)
            out[k] = {"shape": list(a.shape), "dtype": str(a.dtype),
                      "nan": int(np.isnan(af).sum()),
                      "mean": [round(float(x), 3) for x in np.nanmean(af, axis=0)],
                      "std": [round(float(x), 3) for x in np.nanstd(af, axis=0)],
                      "rms": [round(float(x), 3) for x in np.sqrt(np.nanmean(af**2, axis=0))],
                      "flatline_cols": [int(i) for i, s in enumerate(np.nanstd(af, axis=0)) if s < 1e-9]}
        return json.dumps(out)

    def dispatch(self, name: str, args: dict) -> str:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name == "dispatch":
            return f"ERROR: unknown tool {name}"
        try:
            return str(fn(**args))
        except TypeError as e:
            return f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {type(e).__name__}: {e}"
