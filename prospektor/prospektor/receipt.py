"""Verification receipts: canonical JSON body + EIP-712 assay attestation.

Prototype. A receipt says what was checked, against which agreed terms and
pinned evidence, by which engine version and key, and what the office
recommends. It does not move funds and does not claim settlement: the
escrow contract's events are the record of what was paid.
"""
from __future__ import annotations

from .canonical import canonical_bytes, sha256_hex
from .engine import ENGINE_NAME, ENGINE_VERSION, VERDICT_CODE, Evaluation, engine_code_sha256
from .gate import ASSAY_TYPES, assay_digest, assay_domain
from .secp256k1 import SignatureError, address_of, pubkey_bytes, public_key, recover, sign

RECEIPT_FORMAT = "prospektor.receipt/0"
RECOMMENDED = {"PASS": "complete", "FAIL": "reject", "HOLD": "none"}


def build_body(*, seq: int, prev: str | None, view, terms: dict, t_hash: str, evaluation: Evaluation,
               assayer_priv: int, issued_at: int, not_before: int, valid_until: int,
               reissue_of: str | None = None) -> dict:
    pub = public_key(assayer_priv)
    job = view.job
    return {
        "receipt_format": RECEIPT_FORMAT,
        "seq": seq,
        "prev_receipt": prev,
        "binding": {
            "chain_id": view.chain_id, "acp": view.acp, "gate": view.gate, "job_id": view.job_id,
            "deliverable": (view.deliverable or "").lower(), "terms_sha256": t_hash,
            "token": view.token, "budget": job["budget"], "client": job["client"],
            "provider": job["provider"], "expired_at": job["expiredAt"],
        },
        "inputs": [{"name": i["name"], "sha256": i["sha256"].lower()} for i in terms["inputs"]],
        "observed": {"job_status": job["status"], "submitted_at": view.submitted_at, "assayed_at": view.now},
        "evaluation": evaluation.as_dict(),
        "engine": {"name": ENGINE_NAME, "version": ENGINE_VERSION, "code_sha256": engine_code_sha256()},
        "assayer": {"address": address_of(pub), "public_key": "0x" + pubkey_bytes(pub).hex()},
        "attestation_window": {"issued_at": issued_at, "not_before": not_before, "valid_until": valid_until},
        "reissue_of": reissue_of,
        "settlement": {"recommended": RECOMMENDED[evaluation.verdict],
                       "note": "Executed only by the escrow's evaluator contract when a relayer posts this "
                               "attestation; HOLD cannot settle. This receipt moves no funds."},
    }


def receipt_hash(body: dict) -> str:
    return sha256_hex(canonical_bytes(body))


def attestation_message(body: dict, r_hash: str) -> dict:
    b, w = body["binding"], body["attestation_window"]
    return {"acp": b["acp"], "jobId": b["job_id"], "deliverable": b["deliverable"], "termsHash": b["terms_sha256"],
            "verdict": VERDICT_CODE[body["evaluation"]["verdict"]], "receiptHash": r_hash,
            "issuedAt": w["issued_at"], "notBefore": w["not_before"], "validUntil": w["valid_until"]}


def seal(body: dict, assayer_priv: int) -> dict:
    """Hash the body, sign the attestation, return the envelope."""
    r_hash = receipt_hash(body)
    msg = attestation_message(body, r_hash)
    b = body["binding"]
    digest = assay_digest(b["chain_id"], b["gate"], msg)
    v, r, s = sign(digest, assayer_priv)
    return {"receipt_sha256": r_hash, "body": body,
            "attestation": {"domain": assay_domain(b["chain_id"], b["gate"]), "primary_type": "Assay",
                            "types": ASSAY_TYPES, "message": msg, "digest": "0x" + digest.hex(),
                            "signature": {"v": v, "r": f"0x{r:064x}", "s": f"0x{s:064x}"}}}


def signature_tuple(env: dict) -> tuple[int, int, int]:
    sig = env["attestation"]["signature"]
    return sig["v"], int(sig["r"], 16), int(sig["s"], 16)


def verify_envelope(env: dict) -> list[str]:
    """Re-derive every hash and the signer. Returns problems; empty means intact."""
    problems = []
    try:
        body = env["body"]
        r_hash = receipt_hash(body)
        if r_hash != env["receipt_sha256"]:
            problems.append("receipt hash does not match its body (body altered)")
        msg = attestation_message(body, r_hash)
        if msg != env["attestation"]["message"]:
            problems.append("attestation message does not match the receipt body")
        b = body["binding"]
        if env["attestation"]["domain"] != assay_domain(b["chain_id"], b["gate"]):
            problems.append("attestation domain does not match the receipt binding")
        digest = assay_digest(b["chain_id"], b["gate"], msg)
        if "0x" + digest.hex() != env["attestation"]["digest"]:
            problems.append("attestation digest mismatch")
        pt = recover(digest, *signature_tuple(env))
        if address_of(pt).lower() != body["assayer"]["address"].lower():
            problems.append("signature was not made by the stated assayer")
        if "0x" + pubkey_bytes(pt).hex() != body["assayer"]["public_key"]:
            problems.append("stated public key does not match the signature")
    except (KeyError, TypeError, ValueError, SignatureError) as exc:
        problems.append(f"malformed receipt: {type(exc).__name__}: {exc}")
    return problems
