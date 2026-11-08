"""Recover the damaged biosignal tape.

Wire format (reverse-engineered from the bytes, verified in explore*.py):
  37 bytes per packet:
    off 0-1 : start marker AB CD
    off 2   : 0x1F constant (packet type/len?)
    off 3-6 : timestamp, uint32 big-endian, milliseconds, steps of 4 (250 Hz)
    off 7-9 : C0 00 00 constant
    off 10-33: 8 channels x int24 big-endian two's complement
               ch1..ch4 live_quad (off 10,13,16,19); ch5..ch8 constant 0x800000 (unused)
    off 34  : checksum = sum(bytes[2..33]) & 0xFF
    off 35-36: end marker DC BA
Walks the whole tape, resynchronises after damage, keeps only checksum-valid packets.
"""
import numpy as np

def s24be(b0, b1, b2):
    v = (b0 << 16) | (b1 << 8) | b2
    return v - (1 << 24) if v & 0x800000 else v

def main():
    raw = open("tape.bin", "rb").read()
    n = len(raw)
    ts_list = []
    ch_list = []
    pos = 0
    accepted = 0
    N = n
    while pos <= N - 37:
        if (raw[pos] == 0xAB and raw[pos + 1] == 0xCD
                and raw[pos + 35] == 0xDC and raw[pos + 36] == 0xBA
                and (sum(raw[pos + 2:pos + 34]) & 0xFF) == raw[pos + 34]):
            ts = int.from_bytes(raw[pos + 3:pos + 7], "big")
            ts_list.append(ts)
            row = [s24be(raw[pos + 10 + 3 * i], raw[pos + 11 + 3 * i], raw[pos + 12 + 3 * i])
                   for i in range(8)]
            ch_list.append(row)
            accepted += 1
            pos += 37
        else:
            pos += 1
    skipped = N - accepted * 37

    board_ms = np.array(ts_list, dtype=np.uint32)
    counts = np.array(ch_list, dtype=np.int32)

    np.savez("parsed_agent.npz", board_ms=board_ms, counts=counts)

    diffs = np.diff(board_ms.astype(np.int64))
    med = float(np.median(diffs))
    rate = 1000.0 / med
    frac4 = float(np.mean(diffs == 4))
    print(f"packets recovered : {accepted}")
    print(f"timestamp step median: {med} ms -> sample rate {rate:.3f} Hz (fraction of +4 steps: {frac4:.4f})")
    print(f"timestamp span: {board_ms[0]} .. {board_ms[-1]} ms")
    for i in range(8):
        col = counts[:, i].astype(float)
        rms = float(np.sqrt(np.mean(col ** 2)))
        print(f"ch{i+1}: rms {rms:12.0f}  min {col.min():9.0f} max {col.max():9.0f} mean {col.mean():10.0f}")
    print(f"bytes skipped (not part of accepted packets): {skipped} of {N}")

if __name__ == "__main__":
    main()
