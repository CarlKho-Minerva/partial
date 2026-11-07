import json
from pathlib import Path

import numpy as np
import pytest

from partial.agent import reconstruct
from partial.corrupt import corrupt
from partial.oracle import cerelog_ref as ref
from partial.score import score
from partial.synth import synth
from partial.tools import Tools


def test_oracle_round_trip():
    rows = [[1, -2, 3, -4, 8388607, -8388608, 0, 7], [10, 20, 30, 40, 50, 60, 70, 80]]
    raw = ref.build_packet(1000, rows[0]) + b"\x00\xab" + ref.build_packet(1004, rows[1])
    ms, counts, st = ref.parse_tape(raw)
    assert ms.tolist() == [1000, 1004]
    assert counts.tolist() == rows
    assert st.packets == 2 and st.skipped_bytes == 2 and st.checksum_failures == 0


def test_oracle_rejects_bad_checksum():
    raw = bytearray(ref.build_packet(5, [0] * 8))
    raw[20] ^= 0xFF
    ms, _, st = ref.parse_tape(bytes(raw))
    assert ms.size == 0 and st.checksum_failures == 1


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    out = tmp_path_factory.mktemp("s") / "clean"
    synth(out, trials=4, seed=3)
    return out


def test_synth_parses_under_oracle(clean):
    meta = json.loads((clean / "meta.json").read_text())
    ms, counts, st = ref.parse_tape((clean / "tape.bin").read_bytes())
    assert st.packets == meta["packets"] and st.checksum_failures == 0 and st.skipped_bytes == 0
    assert np.all(np.diff(ms.astype(np.int64)) == 4)
    assert counts.shape[1] == 8
    assert (clean / "events.csv").read_text().startswith("trial,label,t_mono,t_unix,action_s,board_ms,sample")
    assert (clean / "reads.csv").read_text().startswith("t_mono,board_ms,packets")


def test_corrupt_is_deterministic_and_breaks_sync(clean, tmp_path):
    a = corrupt(clean, tmp_path / "a", seed=7)
    b = corrupt(clean, tmp_path / "b", seed=7)
    assert a["applied"] == b["applied"]
    assert (tmp_path / "a" / "tape.bin").read_bytes() == (tmp_path / "b" / "tape.bin").read_bytes()
    assert not (tmp_path / "a" / "meta.json").exists()
    assert not (tmp_path / "a" / "reads.csv").exists()
    assert not (tmp_path / "a" / "DAMAGE.json").exists()
    _, _, st = ref.parse_tape((tmp_path / "a" / "tape.bin").read_bytes())
    assert st.skipped_bytes > 0 and st.checksum_failures > 0
    c = corrupt(clean, tmp_path / "c", seed=8)
    assert c["applied"] != a["applied"]


def test_synth_rejects_zero_trials(tmp_path):
    with pytest.raises(ValueError):
        synth(tmp_path / "z", trials=0)


def test_corrupt_rejects_unknown_damage(clean, tmp_path):
    with pytest.raises(ValueError):
        corrupt(clean, tmp_path / "x", damage=["set_fire"])


def test_tools_stay_inside_session(clean):
    t = Tools(clean)
    with pytest.raises(ValueError):
        t.read_text("../../etc/passwd")
    assert "escapes" in t.dispatch("read_text", {"path": "../x"})
    assert t.dispatch("nope", {}).startswith("ERROR")
    assert "ABCD" in t.find_bytes("tape.bin", "ab cd")
    assert t.hexdump("tape.bin", 0, 10 ** 9).count("\n") <= 2048 // 16 + 1


def test_scorer_perfect_and_wrong(clean, tmp_path):
    # a perfect reconstruction: the oracle's own parse plus true claims
    ms, counts, _ = ref.parse_tape((clean / "tape.bin").read_bytes())
    np.savez(clean / "parsed_agent.npz", board_ms=ms, counts=counts)
    events = [l.split(",") for l in (clean / "events.csv").read_text().splitlines()[1:]]
    c = lambda v: {"value": v, "status": "observed", "evidence": "test", "confidence": 1.0}
    rec = {"wire_format": {"packet_length": c(37), "start_marker": c("ABCD"), "end_marker": c("DCBA"),
                           "timestamp": c("u32"), "n_channels": c(8), "sample_encoding": c("int24 big-endian"),
                           "checksum": c("sum(bytes[2:34]) & 0xFF")},
           "sample_rate_hz": c(250.0), "lsb_volts": c(ref.lsb_volts()), "packets_recovered": c(int(ms.size)),
           "bytes_skipped": c(0), "usable_channels": c([1, 2, 3, 4]),
           "trials": [{"trial": int(e[0]), "label": c(e[1]), "sample": c(int(e[6]))} for e in events],
           "what_is_missing": [], "summary": "x"}
    (clean / "reconstruction.json").write_text(json.dumps(rec))
    assert score(clean, clean)["total"] == 1.0
    # a wrong one: bad labels marked observed, wrong rate, wrong channel count
    rec["sample_rate_hz"] = c(500.0)
    rec["wire_format"]["n_channels"] = c(4)
    for tr in rec["trials"]:
        tr["label"] = c("banana")
    (clean / "reconstruction.json").write_text(json.dumps(rec))
    res = score(clean, clean)
    assert res["total"] < 0.8 and any("marked observed" in n for n in res["notes"])
    for f in ("parsed_agent.npz", "reconstruction.json"):
        (clean / f).unlink()


def test_fake_model_loop_end_to_end(clean, tmp_path):
    dmg = tmp_path / "dmg"
    corrupt(clean, dmg, seed=2)
    log = reconstruct(dmg, fake_model=True, verbose=False)
    assert log.stopped == "final"
    rec = json.loads((dmg / "reconstruction.json").read_text())
    assert rec["wire_format"]["packet_length"]["value"] == 37
    assert (dmg / "parsed_agent.npz").exists() and (dmg / "figures" / "overview.png").exists()
    res = score(dmg, clean)
    assert res["total"] > 0.85
    assert (dmg / "agent_log.jsonl").read_text().count("\n") == len(log.steps)
    # with meta.json gone the agent cannot know how many trials existed, so it lists only
    # the surviving ones; when meta survives, the missing labels are null and inferred
    assert all(t["label"]["value"] is not None for t in rec["trials"])
    dmg2 = tmp_path / "dmg2"
    corrupt(clean, dmg2, seed=2, damage=["truncate_events", "garbage_bytes"])
    reconstruct(dmg2, fake_model=True, verbose=False)
    rec2 = json.loads((dmg2 / "reconstruction.json").read_text())
    nulls = [t for t in rec2["trials"] if t["label"]["value"] is None]
    assert nulls and all(t["label"]["status"] == "inferred" for t in nulls)
    assert rec2["lsb_volts"]["status"] == "observed"
