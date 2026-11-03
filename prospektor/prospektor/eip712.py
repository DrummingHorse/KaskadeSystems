"""EIP-712 typed-data hashing (the subset of types this prototype needs).

Supports atomic types (address, bool, uintN, intN, bytes1..bytes32),
dynamic `string` and `bytes`, nested struct types and arrays of these.
Checked against the test vector published with EIP-712 (Example.js:
Mail/Person, private key keccak256("cow")).
"""
from __future__ import annotations

import re

from .keccak import keccak256

_DOMAIN_FIELDS = (
    ("name", "string"),
    ("version", "string"),
    ("chainId", "uint256"),
    ("verifyingContract", "address"),
    ("salt", "bytes32"),
)

_ARRAY = re.compile(r"^(.+)\[(\d*)\]$")


def domain_type(domain: dict) -> list[dict]:
    return [{"name": n, "type": t} for n, t in _DOMAIN_FIELDS if n in domain]


def _deps(primary: str, types: dict, found: set) -> set:
    base = _ARRAY.sub(r"\1", primary)
    while _ARRAY.match(base):
        base = _ARRAY.sub(r"\1", base)
    if base in found or base not in types:
        return found
    found.add(base)
    for field in types[base]:
        _deps(field["type"], types, found)
    return found


def encode_type(primary: str, types: dict) -> str:
    deps = _deps(primary, types, set())
    deps.discard(primary)
    order = [primary] + sorted(deps)
    return "".join(f"{t}(" + ",".join(f"{f['type']} {f['name']}" for f in types[t]) + ")" for t in order)


def type_hash(primary: str, types: dict) -> bytes:
    return keccak256(encode_type(primary, types).encode("utf-8"))


def _as_bytes(value) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str) and value.startswith("0x"):
        return bytes.fromhex(value[2:])
    raise TypeError(f"expected bytes or 0x-hex, got {type(value).__name__}")


def _encode_value(typ: str, value, types: dict) -> bytes:
    m = _ARRAY.match(typ)
    if m:
        inner, length = m.group(1), m.group(2)
        if length and len(value) != int(length):
            raise ValueError(f"{typ}: expected {length} elements")
        return keccak256(b"".join(_encode_value(inner, v, types) for v in value))
    if typ in types:
        return hash_struct(typ, value, types)
    if typ == "string":
        if not isinstance(value, str):
            raise TypeError("string field requires str")
        return keccak256(value.encode("utf-8"))
    if typ == "bytes":
        return keccak256(_as_bytes(value))
    if typ == "bool":
        if not isinstance(value, bool):
            raise TypeError("bool field requires bool")
        return int(value).to_bytes(32, "big")
    if typ == "address":
        raw = _as_bytes(value)
        if len(raw) != 20:
            raise ValueError("address must be 20 bytes")
        return raw.rjust(32, b"\x00")
    if typ.startswith("uint"):
        bits = int(typ[4:] or 256)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < (1 << bits):
            raise ValueError(f"{typ} out of range: {value!r}")
        return value.to_bytes(32, "big")
    if typ.startswith("int"):
        bits = int(typ[3:] or 256)
        if isinstance(value, bool) or not isinstance(value, int) or not -(1 << (bits - 1)) <= value < (1 << (bits - 1)):
            raise ValueError(f"{typ} out of range: {value!r}")
        return (value % (1 << 256)).to_bytes(32, "big")
    if typ.startswith("bytes"):
        size = int(typ[5:])
        raw = _as_bytes(value)
        if not 1 <= size <= 32 or len(raw) != size:
            raise ValueError(f"{typ} must be exactly {size} bytes")
        return raw.ljust(32, b"\x00")
    raise ValueError(f"unsupported EIP-712 type: {typ}")


def encode_data(primary: str, data: dict, types: dict) -> bytes:
    fields = types[primary]
    extra = set(data) - {f["name"] for f in fields}
    if extra:
        raise ValueError(f"{primary}: unexpected fields {sorted(extra)}")
    return type_hash(primary, types) + b"".join(_encode_value(f["type"], data[f["name"]], types) for f in fields)


def hash_struct(primary: str, data: dict, types: dict) -> bytes:
    return keccak256(encode_data(primary, data, types))


def domain_separator(domain: dict) -> bytes:
    return hash_struct("EIP712Domain", domain, {"EIP712Domain": domain_type(domain)})


def digest(domain: dict, primary: str, message: dict, types: dict) -> bytes:
    all_types = dict(types)
    all_types["EIP712Domain"] = domain_type(domain)
    return keccak256(b"\x19\x01" + domain_separator(domain) + hash_struct(primary, message, all_types))
