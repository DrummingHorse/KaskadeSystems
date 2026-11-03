"""Seeded property tests: an independent answer key, mutation fuzzing, and lifecycle invariants.

The answer key below is written from the terms' plain-language criteria and does not
import prospektor.checks. The engine must agree with it on every generated roster, and
must never PASS anything the key rejects. Seeds are fixed, so every run is identical.
"""
import hashlib
import json
import os
import random
import string
import unittest

from prospektor.chain import Revert
from prospektor.engine import FAIL, evaluate
from prospektor.gate import PASS_CODE, assay_digest
from prospektor.office import IntakeRefused
from prospektor.secp256k1 import sign
from prospektor.world import HOUR

from helpers import EVENT, GOOD, WorldCase, good_pairs, roster
from test_engine import TERMS

EV = json.loads(EVENT)
SHIFT = {s["id"]: s for s in EV["shifts"]}
VOL = {v["id"]: v for v in EV["volunteers"]}


def answer_key(doc, shifts=None, vols=None, min_rest=30, max_minutes=600) -> bool:
    """True iff the roster satisfies every agreed criterion (C1-C9), computed independently."""
    SHIFT = shifts or globals()["SHIFT"]
    VOL = vols or globals()["VOL"]
    if not isinstance(doc, dict) or set(doc) - {"format", "assignments", "notes"} or \
            not {"format", "assignments"} <= set(doc) or doc["format"] != "prospektor.roster/0":
        return False
    if "notes" in doc and not (isinstance(doc["notes"], str) and len(doc["notes"]) <= 4000):
        return False
    a = doc["assignments"]
    if not isinstance(a, list) or not 1 <= len(a) <= 5000:
        return False
    pairs = []
    for item in a:
        if not (isinstance(item, dict) and set(item) == {"shift", "volunteer"}):
            return False
        s, v = item["shift"], item["volunteer"]
        ok_id = lambda x: isinstance(x, str) and 1 <= len(x) <= 32 and all(
            c in string.ascii_letters + string.digits + "_-" for c in x)
        if not (ok_id(s) and ok_id(v)):
            return False
        pairs.append((s, v))
    if len(set(pairs)) != len(pairs):
        return False
    if any(s not in SHIFT or v not in VOL for s, v in pairs):
        return False
    for sid, sh in SHIFT.items():
        if sum(1 for s, _ in pairs if s == sid) != sh["needed"]:
            return False
    for s, v in pairs:
        sh, vo = SHIFT[s], VOL[v]
        if sh["skill"] not in vo["skills"]:
            return False
        if not any(lo <= sh["start"] and sh["end"] <= hi for lo, hi in vo["available"]):
            return False
    for vid in VOL:
        mine = sorted((SHIFT[s]["start"], SHIFT[s]["end"]) for s, v in pairs if v == vid)
        if sum(e - b for b, e in mine) > max_minutes:
            return False
        for (b1, e1), (b2, e2) in zip(mine, mine[1:]):
            if b2 < e1 or b2 - e1 < min_rest:
                return False
    return True


def engine_view(bundle):
    ev = evaluate(TERMS, {"event": EVENT}, bundle, None)
    criteria_pass = all(f.result == "pass" for f in ev.findings if f.stage in ("streak", "fire"))
    return ev, criteria_pass


class AnswerKeyAgreement(unittest.TestCase):
    def check(self, doc_or_bytes):
        bundle = doc_or_bytes if isinstance(doc_or_bytes, bytes) else json.dumps(doc_or_bytes).encode()
        ev, engine_ok = engine_view(bundle)
        try:
            key_ok = answer_key(json.loads(bundle))
        except (ValueError, RecursionError):
            key_ok = False
        self.assertEqual(engine_ok, key_ok, bundle[:200])
        if not key_ok:
            self.assertEqual(ev.verdict, FAIL, bundle[:200])
        return key_ok

    def test_good_roster(self):
        self.assertTrue(self.check(GOOD))

    def test_mutations(self):
        rng = random.Random(20261102)
        base = json.loads(GOOD)
        sids, vids = list(SHIFT) + ["S99", "s01"], list(VOL) + ["V99", ""]
        valid = invalid = 0
        for _ in range(1500):
            doc = json.loads(json.dumps(base))
            for _ in range(rng.randint(1, 3)):
                a = doc["assignments"]
                op = rng.randrange(9)
                if op == 0 and a:
                    a.pop(rng.randrange(len(a)))
                elif op == 1:
                    a.append({"shift": rng.choice(sids), "volunteer": rng.choice(vids)})
                elif op == 2 and a:
                    a[rng.randrange(len(a))]["volunteer"] = rng.choice(vids)
                elif op == 3 and a:
                    a[rng.randrange(len(a))]["shift"] = rng.choice(sids)
                elif op == 4 and len(a) > 1:
                    i, k = rng.sample(range(len(a)), 2)
                    a[i]["volunteer"], a[k]["volunteer"] = a[k]["volunteer"], a[i]["volunteer"]
                elif op == 5 and a:
                    a.append(dict(rng.choice(a)))
                elif op == 6:
                    doc[rng.choice(["extra", "notes", "format"])] = rng.choice([1, "x", None, "prospektor.roster/0"])
                elif op == 7 and a:
                    a[rng.randrange(len(a))][rng.choice(["shift", "volunteer", "x"])] = rng.choice([7, None, "S01"])
                elif op == 8:
                    rng.shuffle(a)
            if self.check(doc):
                valid += 1
            else:
                invalid += 1
        self.assertGreater(valid, 50)    # the generator reaches both sides of the boundary
        self.assertGreater(invalid, 1000)
        if os.environ.get("PK_STATS"):
            print(f"\n[stats] mutations: {valid} valid, {invalid} invalid; engine agreed with the key on all")

    def test_random_rosters_from_scratch(self):
        rng = random.Random(8004)
        hits = 0
        for _ in range(1500):
            pairs = []
            for sid, sh in SHIFT.items():
                fits = [v for v, vo in VOL.items() if sh["skill"] in vo["skills"]
                        and any(lo <= sh["start"] and sh["end"] <= hi for lo, hi in vo["available"])]
                pool = [v for v in (fits if rng.random() < 0.8 else VOL) if rng.random() < 0.9]
                rng.shuffle(pool)
                pairs += [(sid, v) for v in pool[: sh["needed"] + rng.choice([0, 0, 0, 0, -1, 1])]]
            hits += self.check(roster(pairs))
        self.assertGreater(hits, 0)
        if os.environ.get("PK_STATS"):
            print(f"\n[stats] random rosters: {hits} valid, {1500 - hits} invalid; engine agreed with the key on all")

    def test_garbage_never_crashes_and_never_passes(self):
        rng = random.Random(402)
        alphabet = b'{}[]":,0123456789abcdefnrtul\\ \x00\xff'
        for _ in range(1500):
            raw = bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 120)))
            ev = evaluate(TERMS, {"event": EVENT}, raw, None)
            self.assertEqual(ev.verdict, FAIL, raw)


KILL_EVENT = {
    "format": "prospektor.event/0", "title": "fictional rule-isolation fixture",
    "shifts": [{"id": "A1", "start": 0, "end": 100, "skill": "x", "needed": 1},
               {"id": "A2", "start": 200, "end": 300, "skill": "x", "needed": 1},
               {"id": "A3", "start": 400, "end": 500, "skill": "y", "needed": 1},
               {"id": "A4", "start": 50, "end": 150, "skill": "x", "needed": 1},
               {"id": "A5", "start": 700, "end": 800, "skill": "y", "needed": 1}],
    "volunteers": [{"id": "P1", "skills": ["x", "y"], "available": [[0, 1000]]},
                   {"id": "P2", "skills": ["x"], "available": [[0, 1000]]},
                   {"id": "P3", "skills": ["y"], "available": [[0, 1000]]},
                   {"id": "P4", "skills": ["x", "y"], "available": [[0, 150]]},
                   {"id": "P5", "skills": [], "available": [[0, 1000]]},
                   {"id": "P6", "skills": ["y"], "available": [[0, 1000]]}],
}
KILL_REST, KILL_MAX = 60, 250
KILL_BASE = {"A1": "P1", "A2": "P2", "A3": "P3", "A4": "P4", "A5": "P6"}


def _case(**changes):
    staff = dict(KILL_BASE, **changes)
    return [(s, v) for s, v in staff.items() if v is not None]


# One roster per rule that violates that rule and nothing else (checked by the first test below).
ISOLATED = {
    "format.roster_v0": None,  # built separately: an extra top-level field
    "roster.no_duplicates": _case() + [("A1", "P1")],
    "roster.refs_exist": _case() + [("Z9", "P1")],
    "roster.coverage": _case(A3=None),
    "roster.qualified": _case(A3="P5"),
    "roster.available": _case(A2="P4", A4="P2"),
    "roster.no_overlap": _case(A4="P1"),
    "roster.min_rest": _case(A1="P2", A4="P1", A2="P1"),
    "roster.max_minutes": _case(A3="P1", A5="P1"),
}


class TheTestsHaveTeeth(unittest.TestCase):
    """Disable each rule in turn; the independent answer key must notice every time."""

    def setUp(self):
        from prospektor.canonical import canonical_bytes
        self.event = canonical_bytes(KILL_EVENT)
        self.terms = json.loads(json.dumps(TERMS))
        self.terms["inputs"][0]["sha256"] = "0x" + hashlib.sha256(self.event).hexdigest()
        for c in self.terms["criteria"]:
            if c["check"] == "roster.min_rest":
                c["params"]["minutes"] = KILL_REST
            if c["check"] == "roster.max_minutes":
                c["params"]["minutes"] = KILL_MAX
        self.cases = {k: roster(v) for k, v in ISOLATED.items() if v is not None}
        doc = json.loads(roster(_case()))
        doc["extra"] = 1
        self.cases["format.roster_v0"] = json.dumps(doc).encode()
        self.cases["(valid)"] = roster(_case())

    def disagreements(self, patched_checks=None):
        from unittest import mock
        from prospektor import checks as chk
        sh = {s["id"]: s for s in KILL_EVENT["shifts"]}
        vo = {v["id"]: v for v in KILL_EVENT["volunteers"]}
        out = []
        with mock.patch("prospektor.engine.CHECKS", patched_checks or chk.CHECKS):
            for name, bundle in self.cases.items():
                ev = evaluate(self.terms, {"event": self.event}, bundle, None)
                engine_ok = all(f.result == "pass" for f in ev.findings if f.stage in ("streak", "fire"))
                key_ok = answer_key(json.loads(bundle), sh, vo, KILL_REST, KILL_MAX)
                if engine_ok != key_ok or (not key_ok and ev.verdict != FAIL):
                    out.append(name)
        return out

    def test_each_isolated_case_violates_exactly_its_rule(self):
        for rule, bundle in self.cases.items():
            ev = evaluate(self.terms, {"event": self.event}, bundle, None)
            fails = sorted({f.check for f in ev.findings if f.result == "fail"})
            self.assertEqual(fails, [] if rule == "(valid)" else [rule], rule)
        self.assertEqual(self.disagreements(), [])

    def test_disabling_any_rule_is_caught(self):
        from prospektor import checks as chk
        for rule, (stage, _, needs) in chk.CHECKS.items():
            if stage == "human":
                continue
            patched = dict(chk.CHECKS)
            patched[rule] = (stage, lambda params, doc, inputs: ("pass", "rule disabled"), needs)
            self.assertIn(rule, self.disagreements(patched), f"disabling {rule} went unnoticed")


class LifecycleInvariants(WorldCase):
    """Random actors take random actions; after every step the money and authority invariants hold."""

    def test_random_walk(self):
        rng = random.Random(183)
        w = self.w
        actors = ["buyer", "provider", "attacker", "relayer"]
        jobs, envs, terms_by_job = [], {}, {}
        minted = w.token.totalSupply()
        settled_by_pass = set()
        ops = (["create"] * 2 + ["submit_random"] + ["deliver"] * 4 + ["assay"] * 4 + ["relay"] * 4
               + ["direct"] + ["refund"] + ["gate"] * 2 + ["forge"] + ["advance"] * 2)
        for step in range(300):
            op = rng.choice(ops)
            who = w.addr(rng.choice(actors))
            try:
                if op == "create" or not jobs:
                    _, tb, th = w.make_terms(challenge_seconds=rng.choice([0, 0, HOUR]))
                    j = w.open_job(th, fund=rng.random() < 0.85)
                    jobs.append(j)
                    terms_by_job[j] = tb
                    continue
                live = [x for x in sorted(envs) if w.acp.getJob(x)["status"] == "Submitted"]
                submitted = [x for x in jobs if w.acp.getJob(x)["status"] == "Submitted"]
                if op in ("relay", "forge") and live:
                    j = rng.choice(live)
                elif op == "assay" and submitted:
                    j = rng.choice(submitted)
                else:
                    j = rng.choice(jobs)
                if op == "submit_random":  # anyone submits a commitment to unknown bytes
                    w.chain.send(who, w.acp, "submit", j, "0x" + rng.randbytes(32).hex())
                elif op == "deliver":
                    w.deliver(j, rng.choice([GOOD, roster(good_pairs()[:-1])]))
                elif op == "assay":
                    sub = w.chain.events_of(w.acp, "JobSubmitted", jobId=j)
                    for bundle in (GOOD, roster(good_pairs()[:-1])):
                        if sub and sub[-1].args["deliverable"] == "0x" + hashlib.sha256(bundle).hexdigest():
                            envs[j] = w.office.assay(j, terms_by_job[j], {"event": EVENT}, bundle)
                elif op == "relay" and j in envs:
                    w.relay([envs[j]], sender=who)
                elif op == "direct":
                    w.chain.send(who, w.acp, rng.choice(["complete", "reject"]), j, "0x" + "00" * 32)
                elif op == "refund":
                    w.chain.send(who, w.acp, "claimRefund", j)
                elif op == "gate" and rng.random() < 0.5:
                    w.chain.send(who, w.gate, "dispute", j, "0x" + "00" * 32)
                elif op == "gate":
                    w.chain.send(who, w.gate, "execute", j)
                elif op == "forge" and j in envs:  # a PASS signed by a key that is not an assayer
                    m = dict(envs[j]["attestation"]["message"], verdict=PASS_CODE)
                    w.chain.send(who, w.gate, "post", [m],
                                 [sign(assay_digest(w.chain.chain_id, w.gate.address, m), w.a["attacker"].priv)])
                elif op == "advance":
                    w.chain.advance(rng.choice([60, 600, HOUR, HOUR, 2 * HOUR, 6 * HOUR, 30 * HOUR]))
            except (Revert, IntakeRefused) as exc:
                self.assertNotIn("InternalError", str(exc))
            # -- invariants --------------------------------------------------------
            b = w.balances()
            self.assertEqual(sum(b.values()), minted)
            live = sum(w.acp.getJob(x)["budget"] for x in jobs if w.acp.getJob(x)["status"] in ("Funded", "Submitted"))
            self.assertEqual(b["escrow"], live, f"step {step}")
            self.assertEqual(b["gate"] + b["assayer"], 0)
            for x in jobs:
                if w.acp.getJob(x)["status"] == "Completed":
                    reason = w.chain.events_of(w.acp, "JobCompleted", jobId=x)[0].args["reason"]
                    env = envs.get(x)
                    self.assertTrue(env and env["receipt_sha256"] == reason and
                                    env["body"]["evaluation"]["verdict"] == "PASS", f"job {x} paid without PASS")
                    settled_by_pass.add(x)
        self.assertGreater(len(jobs), 10)
        statuses = {w.acp.getJob(x)["status"] for x in jobs}
        self.assertGreaterEqual(len(statuses), 5, statuses)  # the walk visits most states
        self.assertGreater(len(settled_by_pass), 0)  # honest payments happened, so the invariant was exercised
        self.assertIn("Rejected", statuses)
        if os.environ.get("PK_STATS"):
            from collections import Counter
            tally = Counter(w.acp.getJob(x)["status"] for x in jobs)
            reverted = sum(1 for tx in w.chain.txs if tx.status == "reverted")
            print(f"\n[stats] random walk: 300 steps, {len(jobs)} jobs {dict(sorted(tally.items()))}, "
                  f"{len(w.chain.txs)} txs ({reverted} reverted), {len(settled_by_pass)} paid, all after PASS")


if __name__ == "__main__":
    unittest.main()
