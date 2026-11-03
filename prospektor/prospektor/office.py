"""The assay office: reads escrow state, runs the engine, signs receipts.

Prototype. The office holds one signing key. It never holds funds and never
sends a transaction: it returns a signed envelope that any party may relay
to the AssayGate. Programmatic interface for agents:

    office.assay(job_id, terms_bytes, {"event": event_bytes}, bundle_bytes) -> envelope
    office.escalation(envelope) -> dict   # for HOLD verdicts and disputes
"""
from __future__ import annotations

from .canonical import StrictJSONError, sha256_hex, strict_loads
from .engine import FAIL, HOLD, PASS, ChainView, Evaluation, Finding, evaluate, terms_hash, validate_terms
from .gate import terms_description
from .ledger import Ledger, input_key
from .receipt import build_body, seal
from .secp256k1 import address_of, public_key


class IntakeRefused(Exception):
    """No verdict was issued: the request is not an assayable delivery for this job."""


class AssayOffice:
    def __init__(self, chain, acp, gate, private_key: int, ledger: Ledger, *, clock=None):
        self.chain, self.acp, self.gate = chain, acp, gate
        self._priv = private_key
        self.address = address_of(public_key(private_key))
        self.ledger = ledger
        self.clock = clock or (lambda: chain.timestamp)

    def read_view(self, job_id: int) -> ChainView:
        """Read the job and its JobSubmitted event from the escrow (chain facts only)."""
        job = self.acp.getJob(job_id)
        subs = self.chain.events_of(self.acp, "JobSubmitted", jobId=job_id)
        return ChainView(chain_id=self.chain.chain_id, acp=self.acp.address, gate=self.gate.address,
                         token=self.acp.paymentToken(), job_id=job_id, job=job,
                         deliverable=subs[-1].args["deliverable"] if subs else None,
                         submitted_at=subs[-1].timestamp if subs else None, now=self.clock())

    def assay(self, job_id: int, terms_bytes: bytes, inputs: dict, bundle: bytes) -> dict:
        try:
            terms = strict_loads(terms_bytes)
        except StrictJSONError as exc:
            raise IntakeRefused(f"terms are not strict JSON: {exc}") from None
        errs = validate_terms(terms)
        if errs:
            raise IntakeRefused("terms are invalid: " + "; ".join(errs))
        t_hash = terms_hash(terms)
        view = self.read_view(job_id)
        # Anti-griefing: only the escrow-committed deliverable, under the escrow-committed
        # terms, is ever assayed. Anything else gets no verdict, so a third party cannot
        # make honest work FAIL by sending the office something else.
        if view.job["description"] != terms_description(t_hash):
            raise IntakeRefused("these terms are not the ones the job's escrow description commits to")
        if view.deliverable is None:
            raise IntakeRefused("the job has no submitted deliverable on-chain")
        if sha256_hex(bundle) != view.deliverable.lower():
            raise IntakeRefused("bytes received do not match the deliverable committed on-chain")

        with self.ledger.session() as led:
            # One terminal verdict per job, durably. While its attestation is current it is
            # returned as is. Once its window lapses unrelayed, the office may re-issue the SAME
            # verdict with a fresh window (otherwise honest work could never be paid), and it
            # never signs the opposite verdict: a disagreement becomes a HOLD for escalation.
            key_job = (view.chain_id, view.acp.lower(), job_id)
            done = led.terminal_for(key_job)
            if done is not None and view.now <= done["body"]["attestation_window"]["valid_until"]:
                return done
            evaluation = evaluate(terms, inputs, bundle, view)
            if done is not None:
                prior = done["body"]["evaluation"]["verdict"]
                if evaluation.verdict in (PASS, FAIL) and evaluation.verdict != prior:
                    evaluation = Evaluation(HOLD, evaluation.findings + [Finding(
                        "intake", "I-office", "office.consistency", "hold",
                        f"re-assay gives {evaluation.verdict}, but receipt {done['receipt_sha256'][:14]}... "
                        f"already signed {prior}; escalated, and the opposite verdict is never signed")],
                        evaluation.stages)
            timing = terms["timing"]
            issued = view.now
            not_before = issued + timing["challenge_seconds"]
            valid_until = min(issued + timing["attestation_ttl_seconds"], view.job["expiredAt"] - 1)
            body = build_body(seq=led.next_seq, prev=led.head, view=view, terms=terms, t_hash=t_hash,
                              evaluation=evaluation, assayer_priv=self._priv, issued_at=issued,
                              not_before=not_before, valid_until=max(valid_until, issued),
                              reissue_of=done["receipt_sha256"] if done is not None else None)
            same = None if done is not None else led.identical(input_key(body))
            if same is not None and same["body"]["evaluation"] == body["evaluation"]:
                return same  # nothing changed since the last (HOLD) receipt: return it, sign nothing new
            env = seal(body, self._priv)
            led.append(env)
            return env

    @staticmethod
    def escalation(env: dict) -> dict:
        """Umpire package for a HOLD (or a disputed decision). Proposal: no umpire service exists."""
        body = env["body"]
        undecided = [f for f in body["evaluation"]["findings"] if f["result"] in ("hold", "not_checked")]
        return {
            "escalation_format": "prospektor.escalation/0",
            "receipt_sha256": env["receipt_sha256"],
            "binding": body["binding"],
            "verdict": body["evaluation"]["verdict"],
            "open_questions": [{"criterion": f["criterion"], "check": f["check"], "detail": f["detail"]}
                               for f in undecided],
            "deadline": body["binding"]["expired_at"],
            "default_if_unresolved": "ERC-8183 claimRefund() after expired_at returns the escrow to the client.",
            "umpire": "Proposal only. No umpire service, dispute rules or fee-shifting are implemented or offered.",
        }
