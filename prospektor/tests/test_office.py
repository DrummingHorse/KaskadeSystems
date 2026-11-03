"""The assay office: intake discipline, office-side faults, durability, restart and concurrency."""
import json
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from prospektor.canonical import canonical_bytes
from prospektor.ledger import Ledger
from prospektor.office import AssayOffice, IntakeRefused
from prospektor.receipt import verify_envelope
from prospektor.world import DAY, HOUR, PRICE

from helpers import BAD, EVENT, GOOD, WorldCase

ROOT = Path(__file__).resolve().parent.parent


def verdict(env):
    return env["body"]["evaluation"]["verdict"]


def failing(env, result="fail"):
    return sorted({f["check"] for f in env["body"]["evaluation"]["findings"] if f["result"] == result})


class Intake(WorldCase):
    def test_only_the_committed_bytes_under_the_committed_terms_get_a_verdict(self):
        j, terms, tb, _ = self.submitted_job(GOOD)
        with self.assertRaisesRegex(IntakeRefused, "do not match the deliverable"):
            self.assay(j, tb, BAD)  # a griefer cannot make honest work FAIL
        other = dict(terms, title="different terms")
        with self.assertRaisesRegex(IntakeRefused, "not the ones the job"):
            self.assay(j, canonical_bytes(other), GOOD)
        with self.assertRaisesRegex(IntakeRefused, "strict JSON"):
            self.assay(j, b"{", GOOD)
        self.assertEqual(self.w.office.ledger.entries(), [])  # nothing signed for any of these

    def test_unsubmitted_job_is_refused(self):
        _, tb, th = self.w.make_terms()
        j = self.w.open_job(th)
        with self.assertRaisesRegex(IntakeRefused, "no submitted deliverable"):
            self.assay(j, tb, GOOD)


class OfficeFaultsHoldNotFail(WorldCase):
    def test_missing_or_wrong_pinned_input(self):
        for inputs in ({}, {"event": EVENT.replace(b"V08", b"V09")}):
            j, _, tb, _ = self.submitted_job(GOOD)
            env = self.assay(j, tb, GOOD, inputs=inputs)
            self.assertEqual(verdict(env), "HOLD")
            self.assertEqual(failing(env), [])

    def test_too_late_to_settle(self):
        _, tb, th = self.w.make_terms(submit_within=DAY)
        j = self.w.open_job(th, expires_in=DAY + 2 * HOUR)
        self.w.chain.advance(DAY)
        self.w.deliver(j, GOOD)
        self.w.chain.advance(2 * HOUR - 300)  # 5 minutes left; terms need a 10-minute settle margin
        env = self.assay(j, tb, GOOD)
        self.assertEqual(verdict(env), "HOLD")
        self.assertIn("timing.settle_window", failing(env, "hold"))

    def test_payment_differs_from_agreed_price(self):
        _, tb, th = self.w.make_terms()
        j = self.w.open_job(th, budget=PRICE + 1)
        self.w.deliver(j, GOOD)
        env = self.assay(j, tb, GOOD)
        self.assertEqual(verdict(env), "HOLD")
        self.assertIn("escrow.payment_terms", failing(env, "hold"))


class ProviderFaultsFail(WorldCase):
    def test_late_delivery_uses_chain_time_not_a_claimed_time(self):
        _, tb, th = self.w.make_terms(submit_within=HOUR)
        j = self.w.open_job(th)
        self.w.chain.advance(2 * HOUR)
        self.w.deliver(j, GOOD)  # nothing in the bytes can claim an earlier time
        env = self.assay(j, tb, GOOD)
        self.assertEqual(verdict(env), "FAIL")
        self.assertEqual(failing(env), ["timing.submitted_by"])


class Durability(WorldCase):
    def test_idempotent_and_restart_safe(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        first = self.assay(j, tb, GOOD)
        self.assertEqual(self.assay(j, tb, GOOD), first)
        restarted = AssayOffice(self.w.chain, self.w.acp, self.w.gate, self.w.a["assayer"].priv,
                                Ledger(self.tmp / "receipts.jsonl"))
        self.assertEqual(restarted.assay(j, tb, {"event": EVENT}, GOOD), first)
        # Even with a changed input after restart, the office never signs a second verdict for the job.
        self.assertEqual(restarted.assay(j, tb, {}, GOOD), first)
        self.assertEqual(len(self.w.office.ledger.entries()), 1)

    def test_hold_can_be_reassayed_when_the_missing_input_arrives(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        held = self.assay(j, tb, GOOD, inputs={})
        self.assertEqual(self.assay(j, tb, GOOD, inputs={}), held)  # nothing changed: nothing new signed
        passed = self.assay(j, tb, GOOD)
        self.assertEqual([verdict(held), verdict(passed)], ["HOLD", "PASS"])
        self.assertEqual(passed["body"]["prev_receipt"], held["receipt_sha256"])

    def test_lapsed_attestation_is_reissued_with_the_same_verdict(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        first = self.assay(j, tb, GOOD)
        self.w.chain.advance(2 * HOUR)  # nobody relayed it within its 1-hour window
        from prospektor.chain import Revert
        with self.assertRaisesRegex(Revert, "AttestationNotCurrent"):
            self.w.relay([first])
        fresh = self.assay(j, tb, GOOD)
        self.assertEqual(verdict(fresh), "PASS")
        self.assertEqual(fresh["body"]["reissue_of"], first["receipt_sha256"])
        self.assertEqual(self.w.relay([fresh]), "settled")

    def test_never_signs_the_opposite_verdict(self):
        from unittest import mock
        from prospektor.engine import FAIL, Evaluation
        j, _, tb, _ = self.submitted_job(GOOD)
        self.assay(j, tb, GOOD)
        self.w.chain.advance(2 * HOUR)
        with mock.patch("prospektor.office.evaluate", return_value=Evaluation(FAIL, [], {})):
            env = self.assay(j, tb, GOOD)
        self.assertEqual(verdict(env), "HOLD")
        self.assertIn("office.consistency", failing(env, "hold"))
        self.assertFalse(any(verdict(e) == "FAIL" for e in self.w.office.ledger.entries()))

    def test_concurrent_assays_sign_one_verdict(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        offices = [AssayOffice(self.w.chain, self.w.acp, self.w.gate, self.w.a["assayer"].priv,
                               Ledger(self.tmp / "receipts.jsonl")) for _ in range(6)]
        out, barrier = [], threading.Barrier(len(offices))

        def go(office):
            barrier.wait()
            out.append(office.assay(j, tb, {"event": EVENT}, GOOD))

        threads = [threading.Thread(target=go, args=(o,)) for o in offices]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len({e["receipt_sha256"] for e in out}), 1)
        self.assertEqual(len(self.w.office.ledger.entries()), 1)


class Receipts(WorldCase):
    def test_any_edit_is_detected(self):
        j, _, tb, _ = self.submitted_job(BAD)
        env = self.assay(j, tb, BAD)
        self.assertEqual(verify_envelope(env), [])
        edits = [("evaluation", "verdict", "PASS"), ("binding", "job_id", 99), ("binding", "budget", 1),
                 ("engine", "code_sha256", "0x" + "0" * 64), ("observed", "submitted_at", 1)]
        for section, key, value in edits:
            bad = json.loads(json.dumps(env))
            bad["body"][section][key] = value
            self.assertTrue(verify_envelope(bad), (section, key))
        swapped = json.loads(json.dumps(env))
        swapped["body"]["assayer"]["public_key"] = "0x04" + "11" * 64
        self.assertTrue(verify_envelope(swapped))

    def test_ledger_detects_deletion_reordering_and_insertion(self):
        for bundle in (GOOD, BAD, GOOD):
            j, _, tb, _ = self.submitted_job(bundle)
            self.assay(j, tb, bundle)
        path = self.tmp / "receipts.jsonl"
        lines = path.read_text().splitlines()
        variants = {"deleted": [lines[0], lines[2]], "reordered": [lines[1], lines[0], lines[2]],
                    "duplicated": lines + [lines[2]]}
        for name, ls in variants.items():
            f = self.tmp / f"{name}.jsonl"
            f.write_text("\n".join(ls) + "\n")
            self.assertTrue(Ledger(f).verify(), name)
        self.assertEqual(Ledger(path).verify(), [])

    def test_engine_logic_hash_is_recorded(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        eng = self.assay(j, tb, GOOD)["body"]["engine"]
        from prospektor.engine import engine_code_sha256
        self.assertEqual(eng["code_sha256"], engine_code_sha256())


class Demo(unittest.TestCase):
    def test_demo_meets_expectations_deterministically_and_verifies_independently(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            from prospektor.demo import run
            s1, s2 = run(d1, quiet=True), run(d2, quiet=True)
            self.assertTrue(s1["ok"])
            self.assertEqual({k: v for k, v in s1.items()}, {k: v for k, v in s2.items()})
            for name in ("receipts.jsonl", "events.jsonl", "transactions.jsonl"):
                self.assertEqual((Path(d1) / name).read_bytes(), (Path(d2) / name).read_bytes(), name)
            res = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_receipts.py"),
                                  str(Path(d1) / "receipts.jsonl"), "--events", str(Path(d1) / "events.jsonl")],
                                 capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertIn("RESULT: verified", res.stdout)


if __name__ == "__main__":
    unittest.main()
