"""secp256k1 ECDSA with Ethereum-style recoverable signatures, standard library only.

Prototype code for local test keys. Nonces are deterministic (RFC 6979,
HMAC-SHA256), signatures are low-s (EIP-2), and v is 27 or 28. The tests
check this module against the EIP-712 specification's signature vector,
well-known key/address pairs, and the OpenSSL-backed `cryptography`
package when it is installed. Arithmetic is not constant-time: do not use
it for keys that protect real funds.
"""
from __future__ import annotations

import hashlib
import hmac

from .keccak import keccak256

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
HALF_N = N // 2


class SignatureError(ValueError):
    pass


def _add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = 3 * x1 * x1 * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _mul(k: int, p):
    result = None
    addend = p
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def _on_curve(pt) -> bool:
    if pt is None:
        return False
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - x * x * x - 7) % P == 0


def public_key(priv: int):
    if not 1 <= priv < N:
        raise ValueError("private key out of range")
    return _mul(priv, G)


def pubkey_bytes(pt) -> bytes:
    """Uncompressed SEC1 encoding: 0x04 || X || Y."""
    return b"\x04" + pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big")


def to_checksum_address(addr20: bytes) -> str:
    """EIP-55 mixed-case hex address."""
    hexaddr = addr20.hex()
    h = keccak256(hexaddr.encode("ascii")).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c for i, c in enumerate(hexaddr))


def address_of(pt) -> str:
    return to_checksum_address(keccak256(pubkey_bytes(pt)[1:])[-20:])


def _rfc6979_k(priv: int, digest: bytes) -> int:
    x = priv.to_bytes(32, "big")
    h = (int.from_bytes(digest, "big") % N).to_bytes(32, "big")
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + x + h, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign(digest: bytes, priv: int) -> tuple[int, int, int]:
    """Sign a 32-byte digest. Returns (v, r, s) with v in {27, 28} and low s."""
    if len(digest) != 32:
        raise ValueError("digest must be 32 bytes")
    if not 1 <= priv < N:
        raise ValueError("private key out of range")
    z = int.from_bytes(digest, "big")
    k = _rfc6979_k(priv, digest)
    rpt = _mul(k, G)
    r = rpt[0] % N
    if r == 0 or rpt[0] >= N:
        raise SignatureError("unusable nonce point; vanishingly rare")
    s = pow(k, -1, N) * (z + r * priv) % N
    if s == 0:
        raise SignatureError("zero s; vanishingly rare")
    recid = rpt[1] & 1
    if s > HALF_N:
        s = N - s
        recid ^= 1
    return 27 + recid, r, s


def recover(digest: bytes, v: int, r: int, s: int):
    """Recover the signer's public key point, enforcing EIP-2 low-s."""
    if len(digest) != 32:
        raise SignatureError("digest must be 32 bytes")
    if v not in (27, 28):
        raise SignatureError("v must be 27 or 28")
    if not (1 <= r < N and 1 <= s <= HALF_N):
        raise SignatureError("r or s out of range (high-s signatures are rejected)")
    x = r
    alpha = (pow(x, 3, P) + 7) % P
    beta = pow(alpha, (P + 1) // 4, P)
    if (beta * beta - alpha) % P:
        raise SignatureError("r is not the x-coordinate of a curve point")
    y = beta if (beta & 1) == (v - 27) else P - beta
    rinv = pow(r, -1, N)
    z = int.from_bytes(digest, "big") % N
    q = _add(_mul(s * rinv % N, (x, y)), _mul((-z * rinv) % N, G))
    if q is None or not _on_curve(q):
        raise SignatureError("recovered point is invalid")
    return q


def recover_address(digest: bytes, v: int, r: int, s: int) -> str:
    return address_of(recover(digest, v, r, s))


def verify(digest: bytes, pt, r: int, s: int) -> bool:
    """Plain ECDSA verification against a known public key (low-s required)."""
    if not (_on_curve(pt) and 1 <= r < N and 1 <= s <= HALF_N and len(digest) == 32):
        return False
    z = int.from_bytes(digest, "big") % N
    w = pow(s, -1, N)
    xy = _add(_mul(z * w % N, G), _mul(r * w % N, pt))
    return xy is not None and xy[0] % N == r


def demo_private_key(label: str) -> int:
    """Deterministic, PUBLIC demo key derived from a label. Never fund these."""
    d = int.from_bytes(hashlib.sha256(b"prospektor-public-demo-key/v0:" + label.encode("utf-8")).digest(), "big")
    return d % (N - 1) + 1
