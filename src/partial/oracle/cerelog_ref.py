"""Held-out ground truth: the Cerelog wire format.

A compact port of the packet format in the vendor's BrainFlow driver
(shakimiansky/Shared_brainflow-cerelog, cerelog.cpp) and of the parser in Carl Kho's
earlier silent-speech-cerelog work (October 2026). It exists so the scorer can check the
agent's reconstruction against what the board really sends. It is never shown to the agent.

Data packet, 37 bytes:
  AB CD | len (=31) | t_ms u32 BE | 3 ADS1299 status bytes | 8 x int24 BE
        | checksum = sum(bytes[2:34]) & 0xFF | DC BA
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

PACKET_LEN = 37
PAYLOAD_LEN = 31
START = b"\xab\xcd"
END = b"\xdc\xba"
N_CHANNELS = 8
FS_HZ = 250.0
VREF_V = 4.5
GAIN = 24
FULL_SCALE = 2**23 - 1


def lsb_volts(gain: int = GAIN) -> float:
    """Input-referred volts per count: (2 * Vref / gain) / 2**24."""
    return (2.0 * VREF_V / gain) / 2**24


def build_packet(t_ms: int, counts, status: bytes = b"\xc0\x00\x00") -> bytes:
    data = bytearray(status)
    for c in counts:
        c = int(max(-FULL_SCALE - 1, min(FULL_SCALE, int(c))))
        data += (c & 0xFFFFFF).to_bytes(3, "big")
    body = bytes([PAYLOAD_LEN]) + struct.pack(">I", t_ms & 0xFFFFFFFF) + bytes(data)
    return START + body + bytes([sum(body) & 0xFF]) + END


@dataclass
class Stats:
    packets: int = 0
    checksum_failures: int = 0
    skipped_bytes: int = 0


def parse_tape(raw: bytes) -> tuple[np.ndarray, np.ndarray, Stats]:
    """Whole-tape parse. Returns (board_ms uint32 (n,), counts int32 (n, 8), stats).
    A packet must pass the length byte, the checksum and the end marker; anything else is
    skipped one byte at a time."""
    st = Stats()
    ts: list[int] = []
    rows: list[list[int]] = []
    pos, n = 0, len(raw)
    while True:
        start = raw.find(START, pos)
        if start < 0 or n - start < PACKET_LEN:
            st.skipped_bytes += n - pos if start < 0 else start - pos
            break
        st.skipped_bytes += start - pos
        pkt = raw[start:start + PACKET_LEN]
        if pkt[2] != PAYLOAD_LEN or pkt[35:37] != END:
            st.skipped_bytes += 1
            pos = start + 1
            continue
        if (sum(pkt[2:34]) & 0xFF) != pkt[34]:
            st.checksum_failures += 1
            st.skipped_bytes += 1
            pos = start + 1
            continue
        ts.append(struct.unpack(">I", pkt[3:7])[0])
        rows.append([int.from_bytes(pkt[10 + 3 * ch:13 + 3 * ch], "big", signed=True)
                     for ch in range(N_CHANNELS)])
        st.packets += 1
        pos = start + PACKET_LEN
    if not ts:
        return np.zeros(0, np.uint32), np.zeros((0, N_CHANNELS), np.int32), st
    return np.array(ts, np.uint32), np.array(rows, np.int32), st
