"""Append-only, hash-chained receipt log with a durable one-verdict-per-job rule.

Prototype. Each line is one signed receipt envelope; each receipt body names
the previous receipt's hash, so editing, deleting or reordering any line
breaks verification from that point on. Settled receipts are also anchored
on-chain as the ERC-8183 `reason`.

The office signs inside `session()`, which holds an exclusive file lock
while it reads the head, checks for an existing verdict, signs and appends
(fsync). So two concurrent requests, or a restart, cannot produce two
different terminal verdicts for the same job. Locking uses fcntl (POSIX);
elsewhere it falls back to an in-process lock only.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

from .receipt import receipt_hash, verify_envelope

_PROCESS_LOCK = threading.Lock()


def job_key(body: dict) -> tuple:
    b = body["binding"]
    return (b["chain_id"], b["acp"].lower(), b["job_id"])


def input_key(body: dict) -> tuple:
    b = body["binding"]
    return job_key(body) + (b["deliverable"], b["terms_sha256"],
                            tuple((i["name"], i["sha256"]) for i in body["inputs"]),
                            body["engine"]["code_sha256"])


class LedgerSession:
    def __init__(self, ledger: "Ledger", entries: list[dict]):
        self.ledger = ledger
        self.entries = entries

    @property
    def head(self) -> str | None:
        return self.entries[-1]["receipt_sha256"] if self.entries else None

    @property
    def next_seq(self) -> int:
        return len(self.entries) + 1

    def terminal_for(self, key: tuple) -> dict | None:
        """The most recent PASS/FAIL receipt for this job, if any."""
        for env in reversed(self.entries):
            if job_key(env["body"]) == key and env["body"]["evaluation"]["verdict"] in ("PASS", "FAIL"):
                return env
        return None

    def identical(self, key: tuple) -> dict | None:
        for env in reversed(self.entries):
            if input_key(env["body"]) == key:
                return env
        return None

    def append(self, env: dict) -> None:
        body = env["body"]
        if body["prev_receipt"] != self.head or body["seq"] != self.next_seq:
            raise RuntimeError("receipt does not extend the current ledger head")
        if verify_envelope(env):
            raise RuntimeError("refusing to append a receipt that does not verify")
        line = json.dumps(env, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with open(self.ledger.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self.entries.append(env)


class Ledger:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock_path = self.path.with_name(self.path.name + ".lock")

    def entries(self) -> list[dict]:
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
        return out

    @contextmanager
    def session(self):
        with _PROCESS_LOCK:
            with open(self._lock_path, "a+") as lock:
                if fcntl:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield LedgerSession(self, self.entries())
                finally:
                    if fcntl:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def verify(self) -> list[str]:
        """Check every signature, hash and chain link. Returns problems (empty = intact)."""
        problems, prev = [], None
        try:
            entries = self.entries()
        except json.JSONDecodeError as exc:
            return [f"ledger line is not valid JSON: {exc}"]
        for n, env in enumerate(entries, 1):
            for p in verify_envelope(env):
                problems.append(f"line {n}: {p}")
            body = env.get("body", {})
            if body.get("seq") != n:
                problems.append(f"line {n}: sequence number {body.get('seq')} out of order")
            if body.get("prev_receipt") != prev:
                problems.append(f"line {n}: does not link to the previous receipt")
            try:
                prev = receipt_hash(body)
            except Exception:
                prev = None
        return problems
