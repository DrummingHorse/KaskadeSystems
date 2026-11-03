"""The staged verification engine: intake -> streak test -> fire assay -> human.

Prototype. `evaluate()` is a pure function of (terms, pinned inputs,
deliverable bytes, chain-observed facts). Same inputs, same engine code
hash: same verdict and findings, byte for byte, on any machine.

Verdict rules (in order):
1. Any intake HOLD (office-side or escrow-setup problem) -> HOLD. Faults on
   the office's side never fail the seller.
2. Any demonstrated violation of an agreed criterion -> FAIL.
3. Anything undecided (human criterion, unknown check, crashed check,
   missing or malformed pinned input) -> HOLD.
4. PASS only if every agreed criterion ran and passed, and the intake
   checks passed against escrow state read from the chain.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .canonical import StrictJSONError, digest_of, sha256_hex, strict_loads
from .checks import CHECKS, INPUT_VALIDATORS

ENGINE_NAME = "prospektor-engine"
ENGINE_VERSION = "0.1.0"
PASS, FAIL, HOLD = "PASS", "FAIL", "HOLD"
VERDICT_CODE = {PASS: 1, FAIL: 2, HOLD: 3}
STAGES = ("intake", "streak", "fire", "human")
TERMS_FORMAT = "prospektor.terms/0"

_LOGIC_FILES = ("canonical.py", "checks.py", "engine.py")
TERMS_PREFIX = "prospektor-terms/0 sha256:"


def terms_description(terms_hash_hex: str) -> str:
    """The exact ERC-8183 job description that commits a job to a terms document."""
    return TERMS_PREFIX + terms_hash_hex.lower()[2:]


def engine_code_sha256() -> str:
    """Hash of the source files that decide verdicts (line endings normalized)."""
    h = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in _LOGIC_FILES:
        data = (here / name).read_bytes().replace(b"\r\n", b"\n")
        h.update(name.encode() + b"\0" + len(data).to_bytes(8, "big") + data)
    return "0x" + h.hexdigest()


@dataclass(frozen=True)
class Finding:
    stage: str
    criterion: str
    check: str
    result: str  # pass | fail | hold | not_checked
    detail: str

    def as_dict(self) -> dict:
        return {"stage": self.stage, "criterion": self.criterion, "check": self.check,
                "result": self.result, "detail": self.detail}


@dataclass(frozen=True)
class ChainView:
    """Facts the office read from the escrow contract, not claims made by a party."""
    chain_id: int
    acp: str
    gate: str
    token: str
    job_id: int
    job: dict
    deliverable: str | None     # from the JobSubmitted event
    submitted_at: int | None    # timestamp of the block containing JobSubmitted
    now: int                    # the office's clock when assaying


@dataclass
class Evaluation:
    verdict: str
    findings: list = field(default_factory=list)
    stages: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        counts = {r: sum(1 for f in self.findings if f.result == r) for r in ("pass", "fail", "hold", "not_checked")}
        return {"verdict": self.verdict, "stages": dict(self.stages), "counts": counts,
                "findings": [f.as_dict() for f in self.findings]}


# ---------------------------------------------------------------------------
# Terms (office-side document; invalid terms are refused before any verdict)
# ---------------------------------------------------------------------------
def validate_terms(terms) -> list[str]:
    errs: list[str] = []
    want = {"terms_format", "title", "job_type", "price", "inputs", "deliverable", "criteria", "timing", "assay"}
    if not isinstance(terms, dict) or set(terms) != want:
        return [f"terms must have exactly these fields: {sorted(want)}"]
    if terms["terms_format"] != TERMS_FORMAT:
        errs.append(f"terms_format must be {TERMS_FORMAT}")
    price = terms["price"]
    if not (isinstance(price, dict) and set(price) == {"token", "amount"} and isinstance(price["amount"], int)
            and not isinstance(price["amount"], bool) and price["amount"] > 0 and isinstance(price["token"], str)):
        errs.append("price must be {token, amount>0}")
    names = set()
    for inp in terms["inputs"] if isinstance(terms["inputs"], list) else [None]:
        if not (isinstance(inp, dict) and set(inp) == {"name", "sha256", "media_type"}
                and isinstance(inp["name"], str) and isinstance(inp["sha256"], str) and len(inp["sha256"]) == 66):
            errs.append("each input must be {name, sha256 (0x + 64 hex), media_type}")
            continue
        names.add(inp["name"])
    d = terms["deliverable"]
    if not (isinstance(d, dict) and set(d) == {"media_type", "max_bytes"} and isinstance(d["max_bytes"], int)
            and 0 < d["max_bytes"] <= 4 * 1024 * 1024):
        errs.append("deliverable must be {media_type, max_bytes in 1..4 MiB}")
    ids = set()
    crit = terms["criteria"]
    if not isinstance(crit, list) or not crit:
        errs.append("criteria must be a non-empty list")
        crit = []
    for c in crit:
        if not (isinstance(c, dict) and set(c) == {"id", "check", "params"} and isinstance(c["id"], str)
                and isinstance(c["check"], str) and isinstance(c["params"], dict)):
            errs.append("each criterion must be {id, check, params}")
            continue
        if c["id"] in ids:
            errs.append(f"criterion id {c['id']} repeated")
        ids.add(c["id"])
    t = terms["timing"]
    tkeys = {"submit_by", "challenge_seconds", "settle_margin_seconds", "attestation_ttl_seconds"}
    if not (isinstance(t, dict) and set(t) == tkeys and all(isinstance(t[k], int) and not isinstance(t[k], bool)
                                                            and t[k] >= 0 for k in tkeys)):
        errs.append(f"timing must have non-negative integers {sorted(tkeys)}")
    a = terms["assay"]
    if not (isinstance(a, dict) and set(a) == {"chain_id", "acp", "gate"}):
        errs.append("assay must be {chain_id, acp, gate}")
    return errs


def terms_hash(terms: dict) -> str:
    return digest_of(terms)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def _intake(terms: dict, t_hash: str, inputs: dict, bundle: bytes, view: ChainView | None) -> list[Finding]:
    out: list[Finding] = []

    def add(crit, check, ok, detail_ok, detail_bad, bad_result=HOLD.lower()):
        out.append(Finding("intake", crit, check, "pass" if ok else bad_result, detail_ok if ok else detail_bad))

    for inp in terms["inputs"]:
        raw = inputs.get(inp["name"])
        if raw is None:
            add("I-input", f"input.{inp['name']}", False, "", f"pinned input '{inp['name']}' was not supplied to the office")
        else:
            got = sha256_hex(raw)
            add("I-input", f"input.{inp['name']}", got == inp["sha256"].lower(),
                f"pinned input '{inp['name']}' matches {inp['sha256'][:12]}...",
                f"pinned input '{inp['name']}' hashes to {got[:12]}..., terms pin {inp['sha256'][:12]}...")

    if view is None:
        out.append(Finding("intake", "I-escrow", "escrow.binding", "not_checked",
                           "offline check: no escrow state read, so this is not an attestation"))
        return out

    job = view.job
    a = terms["assay"]
    add("I-escrow", "escrow.addresses",
        a["chain_id"] == view.chain_id and a["acp"].lower() == view.acp.lower() and a["gate"].lower() == view.gate.lower(),
        "terms name this chain, escrow contract and gate", "terms name a different chain, escrow contract or gate")
    add("I-escrow", "escrow.terms_commitment", job["description"] == terms_description(t_hash),
        "job description commits to these terms", "job description does not commit to these terms")
    add("I-escrow", "escrow.evaluator_and_hook",
        job["evaluator"].lower() == view.gate.lower() and job["hook"].lower() == view.gate.lower(),
        "gate is the job's evaluator and hook", "gate is not both evaluator and hook for this job")
    add("I-escrow", "escrow.status", job["status"] == "Submitted",
        "job is Submitted", f"job status is {job['status']}, not Submitted")
    committed = (view.deliverable or "").lower()
    add("I-escrow", "escrow.deliverable_commitment", committed == sha256_hex(bundle),
        "deliverable bytes match the on-chain commitment", "deliverable bytes do not match the on-chain commitment")
    add("I-escrow", "escrow.payment_terms",
        job["budget"] == terms["price"]["amount"] and view.token.lower() == terms["price"]["token"].lower(),
        f"escrowed budget {job['budget']} equals the agreed price",
        f"escrowed budget {job['budget']} or token differs from the agreed price {terms['price']['amount']}")
    timing = terms["timing"]
    if view.submitted_at is None:
        add("I-timing", "timing.submitted_by", False, "", "no JobSubmitted event found")
    else:
        late = view.submitted_at > timing["submit_by"]
        out.append(Finding("intake", "I-timing", "timing.submitted_by", "fail" if late else "pass",
                           f"submitted at {view.submitted_at}, after the agreed deadline {timing['submit_by']}" if late
                           else f"submitted at {view.submitted_at}, by the agreed deadline {timing['submit_by']}"))
    settle_by = view.now + timing["challenge_seconds"] + timing["settle_margin_seconds"]
    add("I-timing", "timing.settle_window", settle_by < job["expiredAt"],
        "enough time remains to settle before the escrow expires",
        f"too late to settle: escrow expires at {job['expiredAt']}, settlement needs until {settle_by}")
    return out


def evaluate(terms: dict, inputs: dict, bundle: bytes, view: ChainView | None) -> Evaluation:
    """Assay one deliverable. Never raises for problems in the deliverable."""
    errs = validate_terms(terms)
    if errs:
        return Evaluation(HOLD, [Finding("intake", "I-terms", "terms.valid", "hold", "; ".join(errs))],
                          {"intake": "hold", "streak": "skipped", "fire": "skipped", "human": "skipped"})
    t_hash = terms_hash(terms)
    findings = _intake(terms, t_hash, inputs, bundle, view)
    stages = {"intake": _stage_result(findings), "streak": "skipped", "fire": "skipped", "human": "skipped"}
    if any(f.result == "hold" for f in findings):
        return Evaluation(HOLD, findings, stages)

    # Streak test: parse and check the deliverable alone.
    crit = terms["criteria"]
    max_bytes = terms["deliverable"]["max_bytes"]
    if len(bundle) > max_bytes:
        findings.append(Finding("streak", "D-size", "deliverable.max_bytes", "fail",
                                f"deliverable is {len(bundle)} bytes; terms allow {max_bytes}"))
        stages["streak"] = "fail"
        return Evaluation(FAIL, findings, stages)
    try:
        doc = strict_loads(bundle)
    except StrictJSONError as exc:
        findings.append(Finding("streak", "D-parse", "deliverable.strict_json", "fail", str(exc)))
        stages["streak"] = "fail"
        return Evaluation(FAIL, findings, stages)

    by_stage = {s: [] for s in ("streak", "fire", "human")}
    for c in crit:
        spec = CHECKS.get(c["check"])
        if spec is None:
            findings.append(Finding("human", c["id"], c["check"], "hold",
                                    f"check '{c['check']}' is not implemented by {ENGINE_NAME} {ENGINE_VERSION}"))
            continue
        by_stage[spec[0]].append((c, spec))

    findings += _run(by_stage["streak"], "streak", doc, {})
    stages["streak"] = _stage_result([f for f in findings if f.stage == "streak"])
    if stages["streak"] != "fail":
        parsed_inputs, input_findings = _load_inputs(terms, inputs)
        findings += input_findings
        if any(f.result == "hold" for f in input_findings):
            findings += [Finding("fire", c["id"], c["check"], "hold", "not run: a pinned input is unusable")
                         for c, _ in by_stage["fire"]]
        else:
            findings += _run(by_stage["fire"], "fire", doc, parsed_inputs)
        stages["fire"] = _stage_result([f for f in findings if f.stage == "fire"])
    findings += _run(by_stage["human"], "human", doc, {})
    stages["human"] = _stage_result([f for f in findings if f.stage == "human"])

    results = {f.result for f in findings}
    verdict = FAIL if "fail" in results else HOLD if "hold" in results or "not_checked" in results else PASS
    if verdict == PASS and view is None:
        verdict = HOLD  # an offline check can never authorize payment
    return Evaluation(verdict, _ordered(findings), stages)


def _run(items, stage, doc, parsed_inputs) -> list[Finding]:
    out = []
    for c, (_, fn, needs) in items:
        try:
            result, detail = fn(c["params"], doc, {k: parsed_inputs[k] for k in needs})
        except Exception as exc:  # an engine fault must never fail the seller
            result, detail = "hold", f"office-side check error ({type(exc).__name__}); not the provider's fault"
        if result not in ("pass", "fail", "hold"):
            result, detail = "hold", "office-side check returned an invalid result"
        out.append(Finding(stage, c["id"], c["check"], result, detail))
    return out


def _load_inputs(terms, inputs) -> tuple[dict, list[Finding]]:
    parsed, out = {}, []
    for inp in terms["inputs"]:
        name = inp["name"]
        try:
            value = strict_loads(inputs[name])
        except StrictJSONError as exc:
            out.append(Finding("fire", "I-input", f"input.{name}", "hold", f"pinned input '{name}' is malformed: {exc}"))
            continue
        validator = INPUT_VALIDATORS.get(name)
        errs = validator(value) if validator else []
        if errs:
            out.append(Finding("fire", "I-input", f"input.{name}", "hold",
                               f"pinned input '{name}' is invalid: " + "; ".join(errs[:3])))
            continue
        parsed[name] = value
    return parsed, out


def _stage_result(fs) -> str:
    rs = {f.result for f in fs}
    if not fs:
        return "empty"
    return "fail" if "fail" in rs else "hold" if "hold" in rs else "not_checked" if "not_checked" in rs else "pass"


def _ordered(findings) -> list[Finding]:
    """Stable sort by stage; within a stage, findings stay in terms order."""
    rank = {s: i for i, s in enumerate(STAGES)}
    return sorted(findings, key=lambda f: rank[f.stage])
