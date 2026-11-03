"""Keccak-256 (the Ethereum hash), standard library only.

Prototype code. Keccak-256 and SHA3-256 share the same permutation and
sponge; they differ only in the padding byte (0x01 vs 0x06). The tests
run this sponge with SHA3 padding against hashlib.sha3_256, which is an
independent implementation, then check the Keccak padding against
published vectors. Not constant-time; never use it to protect real keys.
"""
from __future__ import annotations

_MASK = (1 << 64) - 1
_RATE = 136  # bytes, for a 256-bit output

_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)

# Rotation offsets r[x][y] for lane (x, y).
_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)

# Precompute rho+pi as (source index, destination index, rotation).
_PI = tuple(
    (x + 5 * y, y + 5 * ((2 * x + 3 * y) % 5), _ROT[x][y])
    for x in range(5) for y in range(5)
)


def _rol(v: int, n: int) -> int:
    n %= 64
    return ((v << n) | (v >> (64 - n))) & _MASK if n else v


def _permute(a: list[int]) -> list[int]:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        a = [a[i] ^ d[i % 5] for i in range(25)]
        b = [0] * 25
        for src, dst, rot in _PI:
            b[dst] = _rol(a[src], rot)
        a = [b[i] ^ (~b[(i + 1) % 5 + 5 * (i // 5)] & b[(i + 2) % 5 + 5 * (i // 5)]) for i in range(25)]
        a[0] ^= rc
    return a


def sponge256(data: bytes, pad_byte: int) -> bytes:
    """256-bit sponge. pad_byte=0x01 gives Keccak-256, 0x06 gives SHA3-256."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes")
    msg = bytearray(data)
    msg.append(pad_byte)
    msg.extend(b"\x00" * ((-len(msg)) % _RATE))
    msg[-1] |= 0x80
    state = [0] * 25
    for off in range(0, len(msg), _RATE):
        block = msg[off:off + _RATE]
        for i in range(_RATE // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        state = _permute(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


def keccak256(data: bytes) -> bytes:
    return sponge256(data, 0x01)
