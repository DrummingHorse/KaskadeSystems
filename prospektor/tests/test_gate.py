"""Settlement authorization: only bound, current, authorized PASS/FAIL attestations move escrow."""
import unittest

from prospektor.chain import Revert
from prospektor.gate import FAIL_CODE, HOLD_CODE, PASS_CODE, assay_digest
from prospektor.receipt import signature_tuple
from prospektor.secp256k1 import N, sign
from prospektor.world import HOUR, PRICE

from helpers import BAD, GOOD, WorldCase


class GateAuthorization(WorldCase):
    def test_pass_completes_fail_rejects(self):
        j1, _, tb1, _ = self.submitted_job(GOOD)
        j2, _, tb2, _ = self.submitted_job(BAD)
        self.assertEqual(self.w.relay([self.assay(j1, tb1, GOOD)]), "settled")
        self.assertEqual(self.w.relay([self.assay(j2, tb2, BAD)]), "settled")
        self.assertEqual(self.w.acp.getJob(j1)["status"], "Completed")
        self.assertEqual(self.w.acp.getJob(j2)["status"], "Rejected")
        self.assertEqual(self.w.token.balanceOf(self.w.addr("provider")), PRICE)

    def test_every_field_is_bound_by_the_signature(self):
        j, _, tb, _ = self.submitted_job(BAD)
        env = self.assay(j, tb, BAD)
        msg, sig = env["attestation"]["message"], signature_tuple(env)
        mutations = {"verdict": PASS_CODE, "receiptHash": "0x" + "00" * 32, "issuedAt": msg["issuedAt"] - 1,
                     "notBefore": msg["notBefore"] + 1, "validUntil": msg["validUntil"] + 1}
        for field, value in mutations.items():
            with self.assertRaises(Revert, msg=field) as cm:
                self.w.chain.send(self.w.addr("provider"), self.w.gate, "post", [dict(msg, **{field: value})], [sig])
            self.assertIn(str(cm.exception), ("UnauthorizedAssayer", "BadSignature"), field)
        self.assertEqual(self.w.acp.getJob(j)["status"], "Submitted")

    def test_replay_onto_identical_job_is_blocked_by_the_signature(self):
        _, tb, th = self.w.make_terms()
        j1, j2 = self.w.open_job(th), self.w.open_job(th)  # same terms, same bytes, different jobs
        self.w.deliver(j1, GOOD)
        self.w.deliver(j2, GOOD)
        env1 = self.assay(j1, tb, GOOD)
        with self.assertRaisesRegex(Revert, "UnauthorizedAssayer"):
            self.w.chain.send(self.w.addr("provider"), self.w.gate, "post",
                              [dict(env1["attestation"]["message"], jobId=j2)], [signature_tuple(env1)])

    def test_other_chain_or_gate_signatures_do_not_recover_to_the_assayer(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        msg = self.assay(j, tb, GOOD)["attestation"]["message"]
        priv = self.w.a["assayer"].priv
        for chain_id, gate in ((1, self.w.gate.address), (self.w.chain.chain_id, self.w.acp.address)):
            sig = sign(assay_digest(chain_id, gate, msg), priv)
            with self.assertRaisesRegex(Revert, "UnauthorizedAssayer"):
                self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post", [msg], [sig])

    def test_hold_and_unknown_verdicts_cannot_settle(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        msg = self.assay(j, tb, GOOD)["attestation"]["message"]
        priv = self.w.a["assayer"].priv
        for verdict, reason in ((HOLD_CODE, "HoldNotSettleable"), (0, "BadVerdict"), (4, "BadVerdict")):
            m = dict(msg, verdict=verdict)  # correctly signed by the real assayer
            with self.assertRaisesRegex(Revert, reason):
                self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post", [m],
                                  [sign(assay_digest(self.w.chain.chain_id, self.w.gate.address, m), priv)])

    def test_high_s_twin_signature_rejected(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        v, r, s = signature_tuple(env)
        with self.assertRaisesRegex(Revert, "BadSignature"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post", [env["attestation"]["message"]],
                              [(55 - v, r, N - s)])

    def test_stale_and_late_attestations(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        self.w.chain.advance(2 * HOUR)  # past validUntil (1 hour TTL)
        with self.assertRaisesRegex(Revert, "AttestationNotCurrent"):
            self.w.relay([env])
        msg = dict(env["attestation"]["message"], notBefore=self.w.acp.getJob(j)["expiredAt"],
                   validUntil=self.w.chain.timestamp + HOUR)
        sig = sign(assay_digest(self.w.chain.chain_id, self.w.gate.address, msg), self.w.a["assayer"].priv)
        with self.assertRaisesRegex(Revert, "WindowPastExpiry"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post", [msg], [sig])

    def test_job_not_wired_to_the_gate_is_refused(self):
        terms, tb, th = self.w.make_terms()
        buyer = self.w.addr("buyer")
        from prospektor.chain import ZERO
        from prospektor.gate import terms_description
        j = self.w.chain.send(buyer, self.w.acp, "createJob", self.w.addr("provider"), self.w.gate.address,
                              self.w.chain.timestamp + 86400 * 3, terms_description(th), ZERO)  # no hook
        self.w.chain.send(buyer, self.w.acp, "setBudget", j, PRICE)
        self.w.chain.send(buyer, self.w.token, "approve", self.w.acp.address, PRICE)
        self.w.chain.send(buyer, self.w.acp, "fund", j, PRICE)
        self.w.deliver(j, GOOD)
        view = self.w.office.read_view(j)
        from prospektor.engine import evaluate
        from prospektor.canonical import strict_loads
        ev = evaluate(strict_loads(tb), {"event": self.w.event_bytes}, GOOD, view)
        self.assertEqual(ev.verdict, "HOLD")  # the office will not attest a job the gate cannot bind
        msg = {"acp": self.w.acp.address, "jobId": j, "deliverable": view.deliverable, "termsHash": th,
               "verdict": PASS_CODE, "receiptHash": "0x" + "11" * 32, "issuedAt": self.w.chain.timestamp,
               "notBefore": self.w.chain.timestamp, "validUntil": self.w.chain.timestamp + 60}
        sig = sign(assay_digest(self.w.chain.chain_id, self.w.gate.address, msg), self.w.a["assayer"].priv)
        with self.assertRaisesRegex(Revert, "GateMustBeHook"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post", [msg], [sig])

    def test_hook_entry_points_are_escrow_only(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        with self.assertRaisesRegex(Revert, "OnlyACP"):
            self.w.chain.send(self.w.addr("attacker"), self.w.gate, "beforeAction", j, "submit", ("0x" + "ee" * 32, b""))
        self.assertEqual(self.w.relay([self.assay(j, tb, GOOD)]), "settled")  # recorded deliverable untouched

    def test_concurrent_relays_settle_exactly_once(self):
        import threading
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        results, gate = [], threading.Barrier(8)

        def go():
            gate.wait()
            try:
                results.append(self.w.relay([env]))
            except Revert as exc:
                results.append(str(exc))

        threads = [threading.Thread(target=go) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count("settled"), 1)
        self.assertEqual(self.w.token.balanceOf(self.w.addr("provider")), PRICE)


class Quorum(WorldCase):
    world_kwargs = {"second_assayer": True, "threshold": 1, "high_value_budget": PRICE, "high_value_threshold": 2}

    def second_opinion(self, env, verdict=None):
        msg = dict(env["attestation"]["message"])
        if verdict is not None:
            msg["verdict"] = verdict
        return msg, sign(assay_digest(self.w.chain.chain_id, self.w.gate.address, msg), self.w.a["assayer-2"].priv)

    def test_high_value_needs_two_independent_keys(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        with self.assertRaisesRegex(Revert, "InsufficientAttestations"):
            self.w.relay([env])
        msg2, sig2 = self.second_opinion(env)
        res = self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post",
                                [env["attestation"]["message"], msg2], [signature_tuple(env), sig2])
        self.assertEqual(res, "settled")

    def test_contradictory_findings_do_not_settle(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        msg2, sig2 = self.second_opinion(env, FAIL_CODE)
        with self.assertRaisesRegex(Revert, "NoConsensus"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post",
                              [env["attestation"]["message"], msg2], [signature_tuple(env), sig2])

    def test_same_key_twice_is_not_a_quorum(self):
        j, _, tb, _ = self.submitted_job(GOOD)
        env = self.assay(j, tb, GOOD)
        with self.assertRaisesRegex(Revert, "DuplicateAssayer|AttestationReplayed"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "post",
                              [env["attestation"]["message"]] * 2, [signature_tuple(env)] * 2)


class ChallengeWindow(WorldCase):
    def pending_job(self):
        j, _, tb, _ = self.submitted_job(GOOD, challenge_seconds=2 * HOUR)
        self.assertEqual(self.w.relay([self.assay(j, tb, GOOD)]), "pending")
        return j

    def test_undisputed_executes_after_window(self):
        j = self.pending_job()
        with self.assertRaisesRegex(Revert, "ChallengeWindowOpen"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "execute", j)
        self.w.chain.advance(2 * HOUR)
        self.w.chain.send(self.w.addr("relayer"), self.w.gate, "execute", j)
        self.assertEqual(self.w.acp.getJob(j)["status"], "Completed")

    def test_only_parties_may_dispute_and_only_in_time(self):
        j = self.pending_job()
        with self.assertRaisesRegex(Revert, "Unauthorized"):
            self.w.chain.send(self.w.addr("attacker"), self.w.gate, "dispute", j, "0x" + "00" * 32)
        self.w.chain.send(self.w.addr("provider"), self.w.gate, "dispute", j, "0x" + "00" * 32)
        with self.assertRaisesRegex(Revert, "AlreadyDisputed"):
            self.w.chain.send(self.w.addr("buyer"), self.w.gate, "dispute", j, "0x" + "00" * 32)
        self.w.chain.advance(2 * HOUR)
        with self.assertRaisesRegex(Revert, "Disputed"):
            self.w.chain.send(self.w.addr("relayer"), self.w.gate, "execute", j)
        j2 = self.pending_job()
        self.w.chain.advance(2 * HOUR)
        with self.assertRaisesRegex(Revert, "ChallengeWindowClosed"):
            self.w.chain.send(self.w.addr("buyer"), self.w.gate, "dispute", j2, "0x" + "00" * 32)

    def test_disputed_job_refunds_at_expiry_and_cannot_pay_after(self):
        j = self.pending_job()
        self.w.chain.send(self.w.addr("buyer"), self.w.gate, "dispute", j, "0x" + "00" * 32)
        self.w.chain.advance(self.w.acp.getJob(j)["expiredAt"] - self.w.chain.timestamp)
        self.w.chain.send(self.w.addr("relayer"), self.w.acp, "claimRefund", j)
        self.assertEqual(self.w.acp.getJob(j)["status"], "Expired")
        self.assertEqual(self.w.token.balanceOf(self.w.addr("provider")), 0)


if __name__ == "__main__":
    unittest.main()
