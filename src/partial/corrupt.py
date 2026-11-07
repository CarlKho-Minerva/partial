"""Damage a session copy in named, reproducible ways. The damage report is written next to
the copy, not inside it, so the agent never sees what was done."""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

DAMAGE = ["drop_meta", "truncate_events", "strip_reads", "garbage_bytes", "cut_range"]


def corrupt(src: Path, dst: Path, seed: int = 1, damage: list[str] | None = None,
            garbage_n: int = 40, cut_frac: float = 0.05) -> dict:
    damage = list(damage) if damage else list(DAMAGE)
    bad = [d for d in damage if d not in DAMAGE]
    if bad:
        raise ValueError(f"unknown damage {bad}; choose from {DAMAGE}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for stale in ("reconstruction.json", "parse_tape.py", "parsed_agent.npz", "figures", "agent_log.jsonl"):
        p = dst / stale
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    rng = random.Random(seed)
    report: dict = {"seed": seed, "applied": []}
    if "drop_meta" in damage and (dst / "meta.json").exists():
        (dst / "meta.json").unlink()
        report["applied"].append("drop_meta: meta.json deleted")
    if "truncate_events" in damage and (dst / "events.csv").exists():
        lines = (dst / "events.csv").read_text().splitlines()
        keep = max(2, len(lines) // 2)
        (dst / "events.csv").write_text("\n".join(lines[:keep]) + "\n")
        report["applied"].append(f"truncate_events: kept {keep - 1} of {len(lines) - 1} rows")
    if "strip_reads" in damage and (dst / "reads.csv").exists():
        (dst / "reads.csv").unlink()
        report["applied"].append("strip_reads: reads.csv deleted")
    tape = bytearray((dst / "tape.bin").read_bytes())
    if "cut_range" in damage and len(tape) > 400:
        n = int(len(tape) * cut_frac)
        at = rng.randrange(37, len(tape) - n - 37)
        del tape[at:at + n]
        report["applied"].append(f"cut_range: removed {n} bytes at offset {at}")
    if "garbage_bytes" in damage:
        spots = sorted(rng.randrange(0, len(tape)) for _ in range(garbage_n))
        for s in spots:
            tape[s] = rng.randrange(256)
        report["applied"].append(f"garbage_bytes: {garbage_n} bytes overwritten")
    (dst / "tape.bin").write_bytes(bytes(tape))
    (dst.parent / f"{dst.name}.damage.json").write_text(json.dumps(report, indent=2))
    return report
