
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
