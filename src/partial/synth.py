"""Make a synthetic recording session in the real session's shape, with no hardware.

Files written (same names and columns as a real Cerelog block):
  tape.bin    raw serial bytes, 37-byte packets at 250 packets/s
  reads.csv   t_mono, board_ms, packets   (one row per host read, ~11 packets per read)
  events.csv  trial, label, t_mono, t_unix, action_s, board_ms, sample
  meta.json   firmware constants, clock map, sites, trial labels, packet count
"""
from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

import numpy as np

from .oracle import cerelog_ref as ref

LABELS = ["rest", "jaw_clench", "lip_purse", "mouth_open", "UP", "DOWN", "LEFT", "RIGHT"]
SITES = {"1": "mental", "2": "submental_mid", "3": "pre_tragus_R", "4": "post_lobule_R"}
ACTIVATION_UV = {"rest": 0.0, "jaw_clench": 60.0, "lip_purse": 25.0, "mouth_open": 35.0,
                 "UP": 12.0, "DOWN": 14.0, "LEFT": 10.0, "RIGHT": 11.0}
HOST_T0 = 92774.0          # host monotonic seconds at handshake (arbitrary, realistic)
BOARD_T0_MS = 2400         # board clock at first packet (the board booted ~2.4 s earlier)
UNIX_T0 = 1792905905.0


def synth(out: Path, trials: int = 8, seed: int = 20261107, rest_s: float = 3.0,
          action_s: float = 2.5, fs: float = ref.FS_HZ) -> dict:
    rng = np.random.default_rng(seed)
    prng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    labels = [prng.choice(LABELS) for _ in range(trials)]
    lead_s = 2.0
    total_s = lead_s + trials * (rest_s + action_s) + 1.0
    n = int(round(total_s * fs))
    period_ms = 1000.0 / fs
    t = np.arange(n) / fs
    lsb = ref.lsb_volts()
    # Floor noise ~4 uV rms on wired channels, big drift on unused ones (as on the real board).
    sig_uv = rng.normal(0, 4.0, size=(n, ref.N_CHANNELS))
    sig_uv[:, 4:] = rng.normal(0, 400.0, size=(n, 4)) + 20000.0 * np.sin(2 * np.pi * 0.1 * t)[:, None]
    # Mains at 60 Hz, small.
    sig_uv[:, :4] += 1.5 * np.sin(2 * np.pi * 60.0 * t)[:, None]
    events = []
    for k, lab in enumerate(labels):
        t_on = lead_s + k * (rest_s + action_s) + rest_s
        a, b = int(t_on * fs), int((t_on + action_s) * fs)
        amp = ACTIVATION_UV[lab]
        if amp > 0:
            # Burst: band-limited noise 20-110 Hz, channel weights by site.
            w = np.array([1.0, 0.8, 0.35, 0.25]) if lab in ("jaw_clench", "mouth_open") else np.array([0.6, 1.0, 0.3, 0.2])
            burst = rng.normal(0, 1.0, size=(b - a, 4))
            env = np.sin(np.pi * np.arange(b - a) / (b - a)) ** 0.5
            sig_uv[a:b, :4] += amp * burst * env[:, None] * w[None, :]
        host_t = HOST_T0 + t_on + rng.uniform(0.0, 0.004)
        events.append({"trial": k, "label": lab, "t_mono": round(host_t, 9),
                       "t_unix": round(UNIX_T0 + t_on, 6), "action_s": action_s,
                       "board_ms": round(BOARD_T0_MS + t_on * 1000.0, 1), "sample": a})
    counts = np.round(sig_uv * 1e-6 / lsb).astype(np.int64)
    board_ms = (BOARD_T0_MS + np.round(np.arange(n) * period_ms)).astype(np.uint32)
    tape = bytearray()
    reads = []
    chunk = 11
    for i in range(n):
        tape += ref.build_packet(int(board_ms[i]), counts[i])
        if (i + 1) % chunk == 0 or i == n - 1:
            latency = 0.0005 + abs(rng.normal(0, 0.0012))
            reads.append((HOST_T0 + i / fs + latency, int(board_ms[i]), i + 1))
    (out / "tape.bin").write_bytes(bytes(tape))
    with open(out / "reads.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_mono", "board_ms", "packets"])
        for r in reads:
            w.writerow([f"{r[0]:.9f}", r[1], r[2]])
    with open(out / "events.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader()
        w.writerows(events)
    # The clock map in the real pipeline is host = a + (1 + b) * board_s; here b = 0.
    a = HOST_T0 - BOARD_T0_MS / 1000.0
    meta = {
        "EXPLORATORY": True, "kind": "block", "synthetic": True, "seed": seed,
        "board_version": "V2", "fs_hz": fs, "gain": ref.GAIN, "lsb_volts": lsb,
        "n_channels": ref.N_CHANNELS, "wired_channels": [1, 2, 3, 4], "sites": SITES,
        "ref_srb1": "mastoid_L", "bias": "clavicle_L", "mode": "silent",
        "firmware_defaults": {"fs_hz": fs, "gain": ref.GAIN, "chnset": 96,
                              "source": "V2_FW.ino register table"},
        "packet_format": {"length": ref.PACKET_LEN, "start": "ABCD", "end": "DCBA",
                          "timestamp": "u32 big-endian ms at byte 3",
                          "samples": "8 x int24 big-endian from byte 10",
                          "checksum": "sum(bytes[2:34]) & 0xFF at byte 34"},
        "clock_map": {"a": a, "b": 0.0, "points": max(3, int(total_s // 5)), "latency_p95_ms": 2.9},
        "handshake_mono": HOST_T0, "handshake_unix": UNIX_T0,
        "packets": n, "tape_bytes": len(tape), "n_events": trials,
        "trials": [{"trial": e["trial"], "label": e["label"]} for e in events],
        "drops": {"dropped": 0, "gaps": 0, "backwards": 0, "effective_fs_hz": fs,
                  "span_s": round((n - 1) * period_ms / 1000.0, 3)},
        "parse": {"checksum_failures": 0, "skipped_bytes": 0},
        "status": "complete",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True))
    return meta
