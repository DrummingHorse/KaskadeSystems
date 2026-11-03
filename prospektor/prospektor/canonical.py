"""Canonical JSON, strict parsing and digests.

Canonical form: object keys sorted (keys must be ASCII), no insignificant
whitespace, UTF-8, integers only (floats, NaN and Infinity are refused).
For these restricted inputs the bytes match RFC 8785 (JCS).

Strict parsing refuses duplicate keys, NaN/Infinity, floats, and nesting
deeper than MAX_DEPTH, so two parsers cannot disagree about what a
document says.
"""
from __future__ import annotations

import hashlib
import json

MAX_DEPTH = 32


class StrictJSONError(ValueError):
    pass


def _check_canonical_value(obj, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise StrictJSONError(f"nesting deeper than {MAX_DEPTH}")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or not k.isascii():
                raise StrictJSONError(f"object keys must be ASCII strings: {k!r}")
            _check_canonical_value(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _check_canonical_value(v, depth + 1)
    elif isinstance(obj, bool) or obj is None or isinstance(obj, str):
        return
    elif isinstance(obj, int):
        return
    else:
        raise StrictJSONError(f"unsupported value type in canonical JSON: {type(obj).__name__}")


def canonical_bytes(obj) -> bytes:
    _check_canonical_value(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return "0x" + hashlib.sha256(data).hexdigest()


def digest_of(obj) -> str:
    return sha256_hex(canonical_bytes(obj))


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise StrictJSONError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _refuse_constant(name):
    raise StrictJSONError(f"non-finite number {name} is not allowed")


def _refuse_float(text):
    raise StrictJSONError(f"non-integer number {text} is not allowed")


def _max_depth(text: str) -> int:
    depth = best = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            best = max(best, depth)
        elif ch in "]}":
            depth -= 1
    return best


def strict_loads(data: bytes):
    """Parse UTF-8 JSON bytes strictly. Raises StrictJSONError on any ambiguity."""
    if not isinstance(data, (bytes, bytearray)):
        raise StrictJSONError("input must be bytes")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONError(f"not valid UTF-8: {exc.reason}") from None
    if text.startswith("﻿"):
        raise StrictJSONError("byte-order mark is not allowed")
    if _max_depth(text) > MAX_DEPTH:
        raise StrictJSONError(f"nesting deeper than {MAX_DEPTH}")
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant,
                          parse_float=_refuse_float)
    except StrictJSONError:
        raise
    except (ValueError, RecursionError) as exc:
        raise StrictJSONError(f"invalid JSON: {exc}") from None
