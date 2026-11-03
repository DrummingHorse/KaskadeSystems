"""AssayGate: an evaluator contract for ERC-8183 jobs, simulated.

Prototype simulation of a contract design; no Solidity version has been
compiled or deployed. ERC-8183 lets the evaluator be a smart contract.
The gate is set as both the job's `evaluator` and its `hook`, and settles
a job only on signed assay attestations:

* PROSPEKTOR never sends a transaction or holds a key that can move
  funds by itself. It signs EIP-712 attestations; anyone may relay them.
* An attestation is bound to chain id, gate, escrow contract, job id, the
  deliverable recorded at submit(), and the terms hash the job's
  description commits to. It cannot be replayed on another job or chain.
* PASS -> complete(), FAIL -> reject(). HOLD can never settle: there is no
  code path from a HOLD attestation to a payment.
* k-of-n independent assayer keys, with a higher k above a budget tier.
* Optional challenge window: client or provider may dispute before the
  decision executes. A disputed decision never executes; under ERC-8183 the
  escrow then refunds the client at expiry (see docs/SECURITY.md, R-2).
* Configuration is fixed at deployment: no admin, no upgrade, no funds.
"""
from __future__ import annotations

import hashlib

from . import eip712
from .acp import SUBMITTED
from .chain import Contract, Revert, require_address, same_address
from .engine import terms_description
from .secp256k1 import SignatureError, recover_address

PASS_CODE, FAIL_CODE, HOLD_CODE = 1, 2, 3
DOMAIN_NAME = "PROSPEKTOR Assay"
DOMAIN_VERSION = "0"

ASSAY_TYPES = {
    "Assay": [
        {"name": "acp", "type": "address"},
        {"name": "jobId", "type": "uint256"},
        {"name": "deliverable", "type": "bytes32"},
        {"name": "termsHash", "type": "bytes32"},
        {"name": "verdict", "type": "uint8"},
        {"name": "receiptHash", "type": "bytes32"},
        {"name": "issuedAt", "type": "uint64"},
        {"name": "notBefore", "type": "uint64"},
        {"name": "validUntil", "type": "uint64"},
    ]
}


def assay_domain(chain_id: int, gate: str) -> dict:
    return {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": chain_id, "verifyingContract": gate}


def assay_digest(chain_id: int, gate: str, message: dict) -> bytes:
    return eip712.digest(assay_domain(chain_id, gate), "Assay", message, ASSAY_TYPES)


def combined_reason(receipt_hashes: list[str]) -> str:
    """bytes32 written on-chain as ERC-8183 `reason`. One receipt: its own hash."""
    if len(receipt_hashes) == 1:
        return receipt_hashes[0].lower()
    joined = b"".join(bytes.fromhex(h[2:]) for h in sorted(h.lower() for h in receipt_hashes))
    return "0x" + hashlib.sha256(joined).hexdigest()


class AssayGate(Contract):
    def __init__(self, chain, address, acp: Contract, assayers: list[str], *, threshold: int = 1,
                 high_value_budget: int | None = None, high_value_threshold: int | None = None):
        super().__init__(chain, address)
        signers = [require_address(a) for a in assayers]
        if not signers or len({a.lower() for a in signers}) != len(signers):
            raise ValueError("assayers must be non-empty and distinct")
        if not 1 <= threshold <= len(signers):
            raise ValueError("threshold out of range")
        if high_value_threshold is not None and not threshold <= high_value_threshold <= len(signers):
            raise ValueError("high_value_threshold out of range")
        self.acp = acp
        self.s.update(assayers=[a.lower() for a in signers], threshold=threshold,
                      high_value_budget=high_value_budget, high_value_threshold=high_value_threshold,
                      deliverables={}, pending={}, disputed={}, consumed={})

    # -- IACPHook (called by the escrow contract only) ---------------------
    def beforeAction(self, job_id: int, selector: str, data: tuple) -> None:
        if not same_address(self.msg_sender, self.acp.address):
            raise Revert("OnlyACP")
        if selector == "submit":
            self.s["deliverables"][job_id] = data[0]

    def afterAction(self, job_id: int, selector: str, data: tuple) -> None:
        if not same_address(self.msg_sender, self.acp.address):
            raise Revert("OnlyACP")

    # -- views ----------------------------------------------------------------
    def required_attestations(self, budget: int) -> int:
        hv_budget, hv_k = self.s["high_value_budget"], self.s["high_value_threshold"]
        if hv_budget is not None and hv_k is not None and budget >= hv_budget:
            return hv_k
        return self.s["threshold"]

    def pendingDecision(self, job_id: int) -> dict | None:
        p = self.s["pending"].get(job_id)
        return dict(p) if p else None

    # -- settlement -------------------------------------------------------------
    def post(self, attestations: list[dict], signatures: list[tuple[int, int, int]]) -> str:
        """Verify attestations for one job; settle now, or queue behind a challenge window."""
        if not attestations or len(attestations) != len(signatures):
            raise Revert("BadInput")
        job_id = attestations[0].get("jobId")
        job = self.call(self.acp, "getJob", job_id)
        if not same_address(job["evaluator"], self.address):
            raise Revert("NotEvaluatorForJob")
        if not same_address(job["hook"], self.address):
            raise Revert("GateMustBeHook")
        if job["status"] != SUBMITTED:
            raise Revert("WrongStatus")
        if self.now >= job["expiredAt"]:
            # ERC-8183 complete() has no expiry check, so a late decision would race
            # claimRefund(). The gate refuses: after expiry the refund path governs.
            raise Revert("JobExpired")
        if job_id in self.s["pending"]:
            raise Revert("AlreadyPending")
        recorded = self.s["deliverables"].get(job_id)
        if recorded is None:
            raise Revert("NoRecordedDeliverable")

        signers, verdicts, receipts, not_before = set(), set(), [], 0
        for att, sig in zip(attestations, signatures):
            if set(att) != {f["name"] for f in ASSAY_TYPES["Assay"]}:
                raise Revert("BadAttestationFields")
            if any(isinstance(att[k], bool) or not isinstance(att[k], int)
                   for k in ("jobId", "verdict", "issuedAt", "notBefore", "validUntil")):
                raise Revert("BadAttestationFields")
            if att["jobId"] != job_id:
                raise Revert("MixedJobs")
            if not same_address(att["acp"], self.acp.address):
                raise Revert("WrongEscrowContract")
            if str(att["deliverable"]).lower() != recorded:
                raise Revert("DeliverableMismatch")
            if not isinstance(att["termsHash"], str) or job["description"] != terms_description(att["termsHash"]):
                raise Revert("TermsMismatch")
            if att["verdict"] == HOLD_CODE:
                raise Revert("HoldNotSettleable")
            if att["verdict"] not in (PASS_CODE, FAIL_CODE):
                raise Revert("BadVerdict")
            if not (att["issuedAt"] <= self.now <= att["validUntil"]):
                raise Revert("AttestationNotCurrent")
            if not (att["issuedAt"] <= att["notBefore"] < job["expiredAt"]):
                raise Revert("WindowPastExpiry")
            try:
                digest = assay_digest(self.chain.chain_id, self.address, att)
                signer = recover_address(digest, *sig).lower()
            except (SignatureError, ValueError, TypeError):
                raise Revert("BadSignature") from None
            if signer not in self.s["assayers"]:
                raise Revert("UnauthorizedAssayer")
            if signer in signers:
                raise Revert("DuplicateAssayer")
            used = f"{digest.hex()}:{signer}"
            if self.s["consumed"].get(used):
                raise Revert("AttestationReplayed")
            signers.add(signer)
            verdicts.add(att["verdict"])
            receipts.append(att["receiptHash"])
            not_before = max(not_before, att["notBefore"])
            self.s["consumed"][used] = True

        if len(verdicts) != 1:
            raise Revert("NoConsensus")
        if len(signers) < self.required_attestations(job["budget"]):
            raise Revert("InsufficientAttestations")
        verdict = verdicts.pop()
        reason = combined_reason(receipts)
        self.emit("DecisionPosted", jobId=job_id, verdict=verdict, reason=reason, notBefore=not_before,
                  assayers=sorted(signers))
        if self.now >= not_before:
            self._settle(job_id, verdict, reason)
            return "settled"
        self.s["pending"][job_id] = {"verdict": verdict, "reason": reason, "notBefore": not_before}
        return "pending"

    def dispute(self, job_id: int, reason_hash: str) -> None:
        pending = self.s["pending"].get(job_id)
        if pending is None:
            raise Revert("NothingPending")
        if self.s["disputed"].get(job_id):
            raise Revert("AlreadyDisputed")
        if self.now >= pending["notBefore"]:
            raise Revert("ChallengeWindowClosed")
        job = self.call(self.acp, "getJob", job_id)
        if not (same_address(self.msg_sender, job["client"]) or same_address(self.msg_sender, job["provider"])):
            raise Revert("Unauthorized")
        self.s["disputed"][job_id] = True
        self.emit("Escalated", jobId=job_id, by=self.msg_sender, reason=reason_hash)

    def execute(self, job_id: int) -> None:
        pending = self.s["pending"].get(job_id)
        if pending is None:
            raise Revert("NothingPending")
        if self.s["disputed"].get(job_id):
            raise Revert("Disputed")
        if self.now < pending["notBefore"]:
            raise Revert("ChallengeWindowOpen")
        job = self.call(self.acp, "getJob", job_id)
        if self.now >= job["expiredAt"]:
            raise Revert("JobExpired")
        del self.s["pending"][job_id]
        self._settle(job_id, pending["verdict"], pending["reason"])

    def _settle(self, job_id: int, verdict: int, reason: str) -> None:
        if verdict == PASS_CODE:
            self.call(self.acp, "complete", job_id, reason)
        elif verdict == FAIL_CODE:
            self.call(self.acp, "reject", job_id, reason)
        else:  # unreachable: post() refuses anything else
            raise Revert("HoldNotSettleable")
        self.emit("Settled", jobId=job_id, verdict=verdict, reason=reason)
