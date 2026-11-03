#!/usr/bin/env python3
"""Independent checker for PROSPEKTOR receipt logs. Imports nothing from the prospektor package.

    python3 tools/verify_receipts.py RECEIPTS.jsonl [--events EVENTS.jsonl] [--assayer 0xADDRESS ...]

What it re-derives, and with what:
  * receipt hashes and chain links ............ hashlib SHA-256 over canonical JSON (re-implemented here)
  * Keccak-256 .................................. a second, separate implementation, which first proves
                                                  its permutation against hashlib.sha3_256 at startup
  * EIP-712 attestation digests ................. hand-encoded for the fixed Assay type
  * ECDSA secp256k1 signatures .................. the `cryptography` package (OpenSSL) if installed,
                                                  else the `openssl` command; never this file's own math
  * assayer address from the public key ......... this file's Keccak
  * on-chain anchoring (with --events) .......... every Completed/Rejected job's reason is a receipt
                                                  hash with the matching verdict, and no HOLD settled

Exit status 0 only if every check passes and signatures were checked by OpenSSL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

# -- Keccak (independent implementation; state as a 5x5 grid of lanes) --------
_R = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = 0xFFFFFFFFFFFFFFFF


def _rc(t):
    r = 1
    for _ in range(t % 255):
        r <<= 1
        if r & 0x100:
            r ^= 0x171
    return r & 1


_RCS = [sum(_rc(j + 7 * i) << ((1 << j) - 1) for j in range(7)) for i in range(24)]


def _f(A):
    for rc in _RCS:
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x + 4) % 5] ^ (((C[(x + 1) % 5] << 1) | (C[(x + 1) % 5] >> 63)) & _M) for x in range(5)]
        A = [[A[x][y] ^ D[x] for y in range(5)] for x in range(5)]
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                n = _R[x][y]
                B[y][(2 * x + 3 * y) % 5] = ((A[x][y] << n) | (A[x][y] >> (64 - n))) & _M if n else A[x][y]
        A = [[B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        A[0][0] ^= rc
    return A


def _sponge(data, pad):
    m = bytearray(data) + bytes([pad])
    while len(m) % 136:
        m.append(0)
    m[-1] |= 0x80
    A = [[0] * 5 for _ in range(5)]
    for off in range(0, len(m), 136):
        for i in range(17):
            A[i % 5][i // 5] ^= int.from_bytes(m[off + 8 * i: off + 8 * i + 8], "little")
        A = _f(A)
    return b"".join(A[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


def keccak(data: bytes) -> bytes:
    return _sponge(data, 0x01)


def _self_test():
    for n in (0, 1, 135, 136, 137, 271, 500):
        msg = bytes((i * 7 + n) % 256 for i in range(n))
        if _sponge(msg, 0x06) != hashlib.sha3_256(msg).digest():
            sys.exit("Keccak self-test FAILED against hashlib.sha3_256; refusing to verify")
    if keccak(b"").hex() != "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470":
        sys.exit("Keccak padding self-test FAILED; refusing to verify")


# -- canonical JSON and EIP-712 for the fixed Assay type ------------------------
def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _w(v: int) -> bytes:
    return v.to_bytes(32, "big")


def _h(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr[2:])


ASSAY = ("Assay(address acp,uint256 jobId,bytes32 deliverable,bytes32 termsHash,uint8 verdict,"
         "bytes32 receiptHash,uint64 issuedAt,uint64 notBefore,uint64 validUntil)")
DOMAIN = "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"


def assay_digest(chain_id: int, gate: str, m: dict) -> bytes:
    dom = keccak(keccak(DOMAIN.encode()) + keccak(b"PROSPEKTOR Assay") + keccak(b"0") + _w(chain_id)
                 + _h(gate).rjust(32, b"\0"))
    st = keccak(keccak(ASSAY.encode()) + _h(m["acp"]).rjust(32, b"\0") + _w(m["jobId"]) + _h(m["deliverable"])
                + _h(m["termsHash"]) + _w(m["verdict"]) + _h(m["receiptHash"]) + _w(m["issuedAt"])
                + _w(m["notBefore"]) + _w(m["validUntil"]))
    return keccak(b"\x19\x01" + dom + st)


def address_from_pubkey(pub: bytes) -> str:
    return "0x" + keccak(pub[1:])[-20:].hex()


# -- ECDSA verification through OpenSSL --------------------------------------
def _der_int(v: int) -> bytes:
    b = v.to_bytes((v.bit_length() + 8) // 8 or 1, "big")
    return b"\x02" + bytes([len(b)]) + b


def _cryptography():
    """The `cryptography` package, or None if missing or broken (some builds panic on import)."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        return InvalidSignature, hashes, ec, utils
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # ImportError, or pyo3's PanicException from a mismatched binary build
        return None


_CRYPTO = _cryptography()


def ecdsa_verify(pub: bytes, digest: bytes, r: int, s: int) -> tuple[bool | None, str]:
    if _CRYPTO is not None:
        InvalidSignature, hashes, ec, utils = _CRYPTO
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256K1(), pub)
        try:
            key.verify(utils.encode_dss_signature(r, s), digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
            return True, "cryptography/OpenSSL"
        except InvalidSignature:
            return False, "cryptography/OpenSSL"
    if not shutil.which("openssl"):
        return None, "unchecked (install `cryptography` or the openssl command)"
    spki = bytes.fromhex("3056301006072a8648ce3d020106052b8104000a034200") + pub
    sig = _der_int(r) + _der_int(s)
    sig = b"\x30" + bytes([len(sig)]) + sig
    with tempfile.TemporaryDirectory() as d:
        paths = {n: os.path.join(d, n) for n in ("pub.der", "dig.bin", "sig.der")}
        for n, data in (("pub.der", spki), ("dig.bin", digest), ("sig.der", sig)):
            with open(paths[n], "wb") as fh:
                fh.write(data)
        res = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-keyform", "DER", "-inkey",
                              paths["pub.der"], "-in", paths["dig.bin"], "-sigfile", paths["sig.der"]],
                             capture_output=True, text=True)
    return res.returncode == 0, "openssl pkeyutl"


# -- main ------------------------------------------------------------------------
VERDICTS = {"PASS": 1, "FAIL": 2, "HOLD": 3}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("receipts")
    ap.add_argument("--events", help="events.jsonl from the same run, to check on-chain anchoring")
    ap.add_argument("--assayer", action="append", default=[], help="expected assayer address (repeatable)")
    args = ap.parse_args(argv)
    _self_test()

    problems, prev, backends, by_hash = [], None, set(), {}
    with open(args.receipts, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip()]
    for n, line in enumerate(lines, 1):
        try:
            env = json.loads(line)
            body, att = env["body"], env["attestation"]
            rh = "0x" + hashlib.sha256(canon(body)).hexdigest()
            if rh != env["receipt_sha256"]:
                problems.append(f"line {n}: body does not hash to receipt_sha256")
            if body["seq"] != n or body["prev_receipt"] != prev:
                problems.append(f"line {n}: broken sequence or chain link")
            prev = rh
            b, w, m = body["binding"], body["attestation_window"], att["message"]
            expect = {"acp": b["acp"], "jobId": b["job_id"], "deliverable": b["deliverable"],
                      "termsHash": b["terms_sha256"], "verdict": VERDICTS[body["evaluation"]["verdict"]],
                      "receiptHash": rh, "issuedAt": w["issued_at"], "notBefore": w["not_before"],
                      "validUntil": w["valid_until"]}
            if m != expect:
                problems.append(f"line {n}: signed message does not match the receipt body")
            digest = assay_digest(b["chain_id"], b["gate"], expect)
            if "0x" + digest.hex() != att["digest"]:
                problems.append(f"line {n}: EIP-712 digest mismatch")
            pub = _h(body["assayer"]["public_key"])
            if address_from_pubkey(pub) != body["assayer"]["address"].lower():
                problems.append(f"line {n}: public key does not belong to the stated assayer address")
            if args.assayer and body["assayer"]["address"].lower() not in {a.lower() for a in args.assayer}:
                problems.append(f"line {n}: signed by an assayer you did not list")
            sig = att["signature"]
            ok, backend = ecdsa_verify(pub, digest, int(sig["r"], 16), int(sig["s"], 16))
            backends.add(backend)
            if ok is False:
                problems.append(f"line {n}: signature does not verify ({backend})")
            by_hash[rh] = body
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            problems.append(f"line {n}: malformed ({type(exc).__name__}: {exc})")

    anchored = 0
    if args.events:
        with open(args.events, encoding="utf-8") as fh:
            events = [json.loads(ln) for ln in fh if ln.strip()]
        for ev in events:
            if ev["event"] not in ("JobCompleted", "JobRejected"):
                continue
            body = by_hash.get(ev["args"]["reason"])
            want = "PASS" if ev["event"] == "JobCompleted" else "FAIL"
            if body is None:
                problems.append(f"job {ev['args']['jobId']}: settled with a reason that is no receipt in this log")
            elif body["evaluation"]["verdict"] != want or body["binding"]["job_id"] != ev["args"]["jobId"]:
                problems.append(f"job {ev['args']['jobId']}: {ev['event']} does not match receipt verdict/job")
            else:
                anchored += 1

    for p in problems:
        print("PROBLEM", p)
    print(f"{len(lines)} receipts checked; signatures via {', '.join(sorted(backends)) or 'none'}"
          + (f"; {anchored} on-chain settlements matched to receipts" if args.events else ""))
    unchecked = any(b.startswith("unchecked") for b in backends)
    if problems or unchecked:
        print("RESULT: NOT VERIFIED")
        return 1
    print("RESULT: verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
