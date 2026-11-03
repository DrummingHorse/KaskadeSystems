"""Shared fixtures for the test suite (fictional data, public demo keys, simulation only)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from prospektor.canonical import canonical_bytes, sha256_hex
from prospektor.world import HOUR, World

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
GOOD = (EXAMPLES / "roster-good.json").read_bytes()
BAD = (EXAMPLES / "roster-double-booked.json").read_bytes()
EVENT = (EXAMPLES / "event.json").read_bytes()


def roster(assignments, notes=None) -> bytes:
    doc = {"format": "prospektor.roster/0", "assignments": [{"shift": s, "volunteer": v} for s, v in assignments]}
    if notes is not None:
        doc["notes"] = notes
    return canonical_bytes(doc)


def good_pairs() -> list[tuple[str, str]]:
    return [(a["shift"], a["volunteer"]) for a in json.loads(GOOD)["assignments"]]


class WorldCase(unittest.TestCase):
    """Each test gets a fresh world and a temporary ledger folder."""

    world_kwargs: dict = {}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pk-test-"))
        self.w = World(self.tmp / "receipts.jsonl", **self.world_kwargs)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def submitted_job(self, bundle: bytes = GOOD, **terms_kw):
        terms, tb, th = self.w.make_terms(**terms_kw)
        job = self.w.open_job(th)
        self.w.chain.advance(HOUR)
        self.w.deliver(job, bundle)
        return job, terms, tb, th

    def assay(self, job, tb, bundle: bytes = GOOD, inputs=None):
        return self.w.office.assay(job, tb, {"event": EVENT} if inputs is None else inputs, bundle)


__all__ = ["BAD", "EVENT", "GOOD", "WorldCase", "good_pairs", "roster", "sha256_hex"]
