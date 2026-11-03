"""ERC-8183 (Agentic Commerce) job escrow, simulated.

Prototype simulation, not a deployed contract. Pinned to the normative text
of ERCS/erc-8183.md in ethereum/ERCs at commit
0da1c2b1b007d073853c89a867ebff62cae539c2 (2 Nov 2026; status Draft;
file sha256 257c35bb...efa3a). See docs/COMPATIBILITY.md.

mode="spec" (default) follows the specification text. mode="reference"
reproduces the deviations of the reference AgenticCommerce.sol embedded in
the same document, so tests can show what they change:

* fund() takes no expectedBudget, so a budget change can front-run funding;
* setBudget() is provider-only (the text says client or provider);
* submit() is also allowed from Open when the budget is zero;
* createJob() requires expiry at least 5 minutes ahead.

Not simulated: ABI encoding, gas, hook gas limits, ERC-165, proxies/upgrades,
ERC-2771 meta-transactions, admin roles.
"""
from __future__ import annotations

from .chain import ZERO, Contract, Revert, require_address, same_address

OPEN, FUNDED, SUBMITTED, COMPLETED, REJECTED, EXPIRED = (
    "Open", "Funded", "Submitted", "Completed", "Rejected", "Expired")
TERMINAL = {COMPLETED, REJECTED, EXPIRED}


def _bytes32(value) -> str:
    if not (isinstance(value, str) and value.startswith("0x") and len(value) == 66):
        raise Revert("InvalidBytes32")
    try:
        bytes.fromhex(value[2:])
    except ValueError:
        raise Revert("InvalidBytes32") from None
    return value.lower()


class AgenticCommerce(Contract):
    def __init__(self, chain, address, payment_token: Contract, treasury: str, *, mode: str = "spec",
                 platform_fee_bp: int = 0, evaluator_fee_bp: int = 0):
        super().__init__(chain, address)
        if mode not in ("spec", "reference"):
            raise ValueError("mode must be 'spec' or 'reference'")
        if platform_fee_bp + evaluator_fee_bp > 10_000:
            raise ValueError("FeesTooHigh")
        self.token = payment_token
        self.mode = mode
        self.s.update(jobs={}, job_counter=0, treasury=treasury, platform_fee_bp=platform_fee_bp,
                      evaluator_fee_bp=evaluator_fee_bp, entered=False)

    # -- views --------------------------------------------------------------
    def getJob(self, job_id: int) -> dict:
        job = self.s["jobs"].get(job_id)
        if job is None:
            raise Revert("InvalidJob")
        return dict(job)

    def paymentToken(self) -> str:
        return self.token.address

    # -- helpers ------------------------------------------------------------
    def _job(self, job_id) -> dict:
        if isinstance(job_id, bool) or not isinstance(job_id, int):
            raise Revert("InvalidJob")
        job = self.s["jobs"].get(job_id)
        if job is None:
            raise Revert("InvalidJob")
        return job

    def _guard(self):
        if self.s["entered"]:
            raise Revert("ReentrancyGuardReentrantCall")
        self.s["entered"] = True

    def _unguard(self):
        self.s["entered"] = False

    def _hook(self, job: dict, phase: str, selector: str, data: tuple) -> None:
        hook = job["hook"]
        if same_address(hook, ZERO):
            return
        target = self.chain.contracts.get(hook)
        if target is None:
            raise Revert("HookMissing")
        self.call(target, "beforeAction" if phase == "before" else "afterAction", job["id"], selector, data)

    # -- lifecycle ----------------------------------------------------------
    def createJob(self, provider: str, evaluator: str, expiredAt: int, description: str, hook: str = ZERO) -> int:
        self._guard()
        try:
            provider, evaluator, hook = require_address(provider), require_address(evaluator), require_address(hook)
            if same_address(evaluator, ZERO):
                raise Revert("ZeroAddress")
            min_expiry = self.now + (300 if self.mode == "reference" else 0)
            if not isinstance(expiredAt, int) or expiredAt <= min_expiry:
                raise Revert("ExpiryTooShort" if self.mode == "reference" else "ExpiryNotInFuture")
            if not isinstance(description, str):
                raise Revert("InvalidDescription")
            if not same_address(hook, ZERO):
                target = self.chain.contracts.get(hook)
                if target is None or not all(callable(getattr(target, f, None)) for f in ("beforeAction", "afterAction")):
                    raise Revert("InvalidJob")  # hook must implement IACPHook
            self.s["job_counter"] += 1
            job_id = self.s["job_counter"]
            self.s["jobs"][job_id] = {"id": job_id, "client": self.msg_sender, "provider": provider,
                                      "evaluator": evaluator, "description": description, "budget": 0,
                                      "expiredAt": expiredAt, "status": OPEN, "hook": hook}
            self.emit("JobCreated", jobId=job_id, client=self.msg_sender, provider=provider,
                      evaluator=evaluator, expiredAt=expiredAt, hook=hook)
            return job_id
        finally:
            self._unguard()

    def setProvider(self, job_id: int, provider: str, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] != OPEN:
                raise Revert("WrongStatus")
            if not same_address(self.msg_sender, job["client"]):
                raise Revert("Unauthorized")
            if not same_address(job["provider"], ZERO):
                raise Revert("WrongStatus")
            provider = require_address(provider)
            if same_address(provider, ZERO):
                raise Revert("ZeroAddress")
            hooked = self.mode == "spec"
            if hooked:
                self._hook(job, "before", "setProvider", (provider, optParams))
            job["provider"] = provider
            self.emit("ProviderSet", jobId=job_id, provider=provider)
            if hooked:
                self._hook(job, "after", "setProvider", (provider, optParams))
        finally:
            self._unguard()

    def setBudget(self, job_id: int, amount: int, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] != OPEN:
                raise Revert("WrongStatus")
            allowed = (job["provider"],) if self.mode == "reference" else (job["client"], job["provider"])
            if not any(same_address(self.msg_sender, a) for a in allowed) or same_address(self.msg_sender, ZERO):
                raise Revert("Unauthorized")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise Revert("InvalidAmount")
            self._hook(job, "before", "setBudget", (amount, optParams))
            job["budget"] = amount
            self.emit("BudgetSet", jobId=job_id, amount=amount)
            self._hook(job, "after", "setBudget", (amount, optParams))
        finally:
            self._unguard()

    def fund(self, job_id: int, expectedBudget: int | None = None, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] != OPEN:
                raise Revert("WrongStatus")
            if not same_address(self.msg_sender, job["client"]):
                raise Revert("Unauthorized")
            if same_address(job["provider"], ZERO):
                raise Revert("ProviderNotSet")
            if self.now >= job["expiredAt"]:
                raise Revert("WrongStatus")  # reference implementation check: no funding after expiry
            if self.mode == "spec":
                if job["budget"] == 0:
                    raise Revert("ZeroBudget")
                if expectedBudget != job["budget"]:
                    raise Revert("BudgetMismatch")  # front-running protection (spec text)
            self._hook(job, "before", "fund", (optParams,))
            job["status"] = FUNDED
            if job["budget"] > 0:
                self.call(self.token, "transferFrom", job["client"], self.address, job["budget"])
            self.emit("JobFunded", jobId=job_id, client=job["client"], amount=job["budget"])
            self._hook(job, "after", "fund", (optParams,))
        finally:
            self._unguard()

    def submit(self, job_id: int, deliverable: str, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            ok = job["status"] == FUNDED or (self.mode == "reference" and job["status"] == OPEN and job["budget"] == 0)
            if not ok:
                raise Revert("WrongStatus")
            if not same_address(self.msg_sender, job["provider"]):
                raise Revert("Unauthorized")
            deliverable = _bytes32(deliverable)
            self._hook(job, "before", "submit", (deliverable, optParams))
            job["status"] = SUBMITTED
            self.emit("JobSubmitted", jobId=job_id, provider=job["provider"], deliverable=deliverable)
            self._hook(job, "after", "submit", (deliverable, optParams))
        finally:
            self._unguard()

    def complete(self, job_id: int, reason: str, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] != SUBMITTED:
                raise Revert("WrongStatus")
            if not same_address(self.msg_sender, job["evaluator"]):
                raise Revert("Unauthorized")
            reason = _bytes32(reason)
            self._hook(job, "before", "complete", (reason, optParams))
            job["status"] = COMPLETED
            amount = job["budget"]
            platform_fee = amount * self.s["platform_fee_bp"] // 10_000
            evaluator_fee = amount * self.s["evaluator_fee_bp"] // 10_000
            net = amount - platform_fee - evaluator_fee
            if platform_fee:
                self.call(self.token, "transfer", self.s["treasury"], platform_fee)
            if evaluator_fee:
                self.call(self.token, "transfer", job["evaluator"], evaluator_fee)
                self.emit("EvaluatorFeePaid", jobId=job_id, evaluator=job["evaluator"], amount=evaluator_fee)
            if net:
                self.call(self.token, "transfer", job["provider"], net)
            self.emit("JobCompleted", jobId=job_id, evaluator=job["evaluator"], reason=reason)
            self.emit("PaymentReleased", jobId=job_id, provider=job["provider"], amount=net)
            self._hook(job, "after", "complete", (reason, optParams))
        finally:
            self._unguard()

    def reject(self, job_id: int, reason: str, optParams: bytes = b"") -> None:
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] == OPEN:
                if not same_address(self.msg_sender, job["client"]):
                    raise Revert("Unauthorized")
            elif job["status"] in (FUNDED, SUBMITTED):
                if not same_address(self.msg_sender, job["evaluator"]):
                    raise Revert("Unauthorized")
            else:
                raise Revert("WrongStatus")
            reason = _bytes32(reason)
            self._hook(job, "before", "reject", (reason, optParams))
            prev = job["status"]
            job["status"] = REJECTED
            if prev in (FUNDED, SUBMITTED) and job["budget"] > 0:
                self.call(self.token, "transfer", job["client"], job["budget"])
                self.emit("Refunded", jobId=job_id, client=job["client"], amount=job["budget"])
            self.emit("JobRejected", jobId=job_id, rejector=self.msg_sender, reason=reason)
            self._hook(job, "after", "reject", (reason, optParams))
        finally:
            self._unguard()

    def claimRefund(self, job_id: int) -> None:
        """Anyone may call after expiry. Deliberately not hookable (spec)."""
        self._guard()
        try:
            job = self._job(job_id)
            if job["status"] not in (FUNDED, SUBMITTED):
                raise Revert("WrongStatus")
            if self.now < job["expiredAt"]:
                raise Revert("WrongStatus")
            job["status"] = EXPIRED
            if job["budget"] > 0:
                self.call(self.token, "transfer", job["client"], job["budget"])
                self.emit("Refunded", jobId=job_id, client=job["client"], amount=job["budget"])
            self.emit("JobExpired", jobId=job_id)
        finally:
            self._unguard()
