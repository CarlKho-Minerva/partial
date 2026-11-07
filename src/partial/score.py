"""Behavioral-equivalence scorer. Compares the agent's parse and claims against the held-out
oracle parse of the same tape and the untouched session's meta.json and events.csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .oracle import cerelog_ref as ref

CLAIM_KEYS = {"value", "status", "evidence", "confidence"}


def _claim_val(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur.get("value") if isinstance(cur, dict) else None


def _walk_claims(obj, path="", out=None):
    out = out if out is not None else []
    if isinstance(obj, dict):
        if CLAIM_KEYS <= set(obj.keys()):
            out.append((path, obj))
            return out
        for k, v in obj.items():
            _walk_claims(v, f"{path}.{k}" if path else k, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_claims(v, f"{path}[{i}]", out)
    return out


def _read_truth_events(truth: Path) -> list[dict]:
    p = truth / "events.csv"
    if not p.exists():
        return []
    with open(p) as fh:
        return [{"trial": int(r["trial"]), "label": r["label"], "sample": int(r["sample"])}
                for r in csv.DictReader(fh)]


def score(session: Path, truth: Path) -> dict:
    """Returns {"rows": [(name, got, want, score)], "total": float, "notes": [...]}."""
    rows: list[tuple[str, str, str, float]] = []
    notes: list[str] = []
    ref_ms, ref_counts, _ = ref.parse_tape((session / "tape.bin").read_bytes())
    tmeta = json.loads((truth / "meta.json").read_text()) if (truth / "meta.json").exists() else {}
    tevents = _read_truth_events(truth)

    # 1. the agent's parse, against the oracle parse of the SAME (damaged) tape
    agent_npz = session / "parsed_agent.npz"
    if agent_npz.exists():
        z = np.load(agent_npz, allow_pickle=False)
        a_ms, a_counts = z["board_ms"], z["counts"]
        if a_counts.ndim == 1:
            a_counts = a_counts[:, None]
        n_ratio = min(a_ms.size, ref_ms.size) / max(a_ms.size, ref_ms.size, 1)
        rows.append(("packets recovered", str(a_ms.size), str(ref_ms.size), round(n_ratio, 3)))
        common, ia, ib = np.intersect1d(a_ms, ref_ms, return_indices=True)
        ts_score = common.size / max(ref_ms.size, 1)
        rows.append(("timestamps matched", str(common.size), str(ref_ms.size), round(ts_score, 3)))
        if common.size and a_counts.shape[1] == ref_counts.shape[1]:
            eq = np.all(a_counts[ia] == ref_counts[ib], axis=1).mean()
        elif common.size:
            eq = 0.0
            notes.append(f"agent parsed {a_counts.shape[1]} channels, oracle has {ref_counts.shape[1]}")
        else:
            eq = 0.0
        rows.append(("samples byte-identical", f"{eq:.3f}", "1.000", round(float(eq), 3)))
    else:
        rows += [("packets recovered", "no parsed_agent.npz", str(ref_ms.size), 0.0),
                 ("timestamps matched", "-", "-", 0.0), ("samples byte-identical", "-", "-", 0.0)]

    # 2. claims in reconstruction.json against the truth
    rec_p = session / "reconstruction.json"
    rec = json.loads(rec_p.read_text()) if rec_p.exists() else {}
    if not rec:
        notes.append("no reconstruction.json")
    wf = rec.get("wire_format", {})

    def num_close(got, want, tol):
        try:
            return float(abs(float(got) - float(want)) <= tol * abs(float(want)))
        except (TypeError, ValueError):
            return 0.0

    rows.append(("packet length", str(_claim_val(wf, "packet_length")), str(ref.PACKET_LEN),
                 float(_claim_val(wf, "packet_length") == ref.PACKET_LEN)))
    sm = str(_claim_val(wf, "start_marker") or "").replace(" ", "").upper()
    rows.append(("start marker", sm or "-", "ABCD", float(sm == "ABCD")))
    em = str(_claim_val(wf, "end_marker") or "").replace(" ", "").upper()
    rows.append(("end marker", em or "-", "DCBA", float(em == "DCBA")))
    rows.append(("channels", str(_claim_val(wf, "n_channels")), str(ref.N_CHANNELS),
                 float(_claim_val(wf, "n_channels") == ref.N_CHANNELS)))
    enc = str(_claim_val(wf, "sample_encoding") or "").lower()
    enc_ok = ("24" in enc) and ("big" in enc)
    rows.append(("sample encoding", enc[:28] or "-", "int24 big-endian", float(enc_ok)))
    ck = str(_claim_val(wf, "checksum") or "").lower().replace(" ", "")
    ck_ok = ("sum" in ck) and ("34" in ck or "0xff" in ck or "255" in ck)
    rows.append(("checksum rule", ck[:28] or "-", "sum(bytes[2:34])&0xFF", float(ck_ok)))
    fs_want = tmeta.get("fs_hz", ref.FS_HZ)
    rows.append(("sample rate (Hz)", str(_claim_val(rec, "sample_rate_hz")), str(fs_want),
                 num_close(_claim_val(rec, "sample_rate_hz"), fs_want, 0.01)))
    lsb_want = tmeta.get("lsb_volts", ref.lsb_volts())
    rows.append(("volts per count", str(_claim_val(rec, "lsb_volts")), f"{lsb_want:.4g}",
                 num_close(_claim_val(rec, "lsb_volts"), lsb_want, 0.02)))
    want_usable = set(tmeta.get("wired_channels", []))
    got_usable = set(_claim_val(rec, "usable_channels") or [])
    if want_usable:
        j = len(want_usable & got_usable) / len(want_usable | got_usable) if (want_usable | got_usable) else 0.0
        rows.append(("usable channels", str(sorted(got_usable)), str(sorted(want_usable)), round(j, 3)))

    # 3. labels: right and honest. An observed label must be right; an inferred null is
    # neither rewarded nor punished; a wrong label marked observed costs double.
    truth_lab = {e["trial"]: e["label"] for e in tevents}
    if truth_lab:
        pts, maxpts, dishonest = 0.0, float(len(truth_lab)), 0
        for tr in rec.get("trials", []):
            k = tr.get("trial")
            lab = tr.get("label", {}) if isinstance(tr.get("label"), dict) else {"value": tr.get("label"), "status": "observed"}
            v, st = lab.get("value"), lab.get("status")
            if k in truth_lab and v is not None:
                if v == truth_lab[k]:
                    pts += 1.0
                elif st == "observed":
                    pts -= 1.0
                    dishonest += 1
        rows.append(("trial labels", f"{pts:g}/{maxpts:g}", f"{maxpts:g}", round(max(0.0, pts) / maxpts, 3)))
        if dishonest:
            notes.append(f"{dishonest} wrong label(s) were marked observed")
    # 4. contract: every claim carries all four keys with a valid status
    claims = _walk_claims(rec)
    ok = sum(1 for _, c in claims if c.get("status") in ("observed", "inferred")
             and isinstance(c.get("confidence"), (int, float)) and 0 <= c["confidence"] <= 1)
    rows.append(("claims with full contract", f"{ok}/{len(claims)}", str(len(claims)),
                 round(ok / len(claims), 3) if claims else 0.0))
    total = round(sum(r[3] for r in rows) / len(rows), 3) if rows else 0.0
    return {"rows": rows, "total": total, "notes": notes}


def format_table(res: dict, title: str = "") -> str:
    w = max(len(r[0]) for r in res["rows"]) + 2
    lines = [title] if title else []
    lines.append(f"{'check':<{w}}{'agent':<24}{'truth':<24}score")
    for name, got, want, s in res["rows"]:
        lines.append(f"{name:<{w}}{got[:22]:<24}{want[:22]:<24}{s:.2f}")
    lines.append(f"{'TOTAL':<{w}}{'':<24}{'':<24}{res['total']:.2f}")
    for n in res["notes"]:
        lines.append(f"  note: {n}")
    return "\n".join(lines)
