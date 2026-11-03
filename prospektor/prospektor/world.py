"""A reproducible local world: chain, test token, ERC-8183 escrow, gate, office, agents.

Prototype. Every key here is a PUBLIC demo key derived from a label
(secp256k1.demo_private_key). They are printed in the demo on purpose.
Never send real funds to these addresses on any network.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .acp import AgenticCommerce
from .canonical import canonical_bytes, sha256_hex, strict_loads
from .chain import Chain, TestToken
from .engine import terms_hash
from .gate import AssayGate, terms_description
from .ledger import Ledger
from .office import AssayOffice
from .receipt import signature_tuple
from .secp256k1 import address_of, demo_private_key, public_key

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
UNIT = 10 ** 6  # tUSD has 6 decimals
PRICE = 250 * UNIT
HOUR, DAY = 3600, 86400
START_TIME = 1_800_000_000  # simulated clock; not wall time


def money(amount: int) -> str:
    return f"{amount // UNIT:,}.{amount % UNIT // 10 ** 4:02d} tUSD"


@dataclass(frozen=True)
class Actor:
    label: str
    priv: int
    address: str


def actor(label: str) -> Actor:
    priv = demo_private_key(label)
    return Actor(label, priv, address_of(public_key(priv)))


class World:
    def __init__(self, ledger_path, *, mode: str = "spec", second_assayer: bool = False, threshold: int = 1,
                 high_value_budget: int | None = None, high_value_threshold: int | None = None,
                 evaluator_fee_bp: int = 0):
        self.chain = Chain(timestamp=START_TIME)
        names = ("deployer", "buyer", "provider", "assayer", "assayer-2", "attacker", "relayer", "treasury")
        self.a = {n: actor(n) for n in names}
        dep = self.a["deployer"].address
        self.token = self.chain.deploy(TestToken, dep, minter=dep)
        self.acp = self.chain.deploy(AgenticCommerce, dep, self.token, self.a["treasury"].address, mode=mode,
                                     evaluator_fee_bp=evaluator_fee_bp)
        signers = [self.a["assayer"].address] + ([self.a["assayer-2"].address] if second_assayer else [])
        self.gate = self.chain.deploy(AssayGate, dep, self.acp, signers, threshold=threshold,
                                      high_value_budget=high_value_budget, high_value_threshold=high_value_threshold)
        self.chain.send(dep, self.token, "mint", self.a["buyer"].address, 10_000 * UNIT)
        self.office = AssayOffice(self.chain, self.acp, self.gate, self.a["assayer"].priv, Ledger(ledger_path))
        self.event_bytes = (EXAMPLES / "event.json").read_bytes()

    # -- helpers --------------------------------------------------------------
    def addr(self, name: str) -> str:
        return self.a[name].address

    def example(self, name: str) -> bytes:
        return (EXAMPLES / name).read_bytes()

    def make_terms(self, *, extra_criteria: tuple = (), challenge_seconds: int = 0,
                   submit_within: int = 2 * DAY, price: int = PRICE) -> tuple[dict, bytes, str]:
        terms = strict_loads((EXAMPLES / "terms-template.json").read_bytes())
        terms["price"] = {"token": self.token.address, "amount": price}
        terms["inputs"][0]["sha256"] = sha256_hex(self.event_bytes)
        terms["criteria"] = terms["criteria"] + [dict(c) for c in extra_criteria]
        terms["timing"]["submit_by"] = self.chain.timestamp + submit_within
        terms["timing"]["challenge_seconds"] = challenge_seconds
        terms["assay"] = {"chain_id": self.chain.chain_id, "acp": self.acp.address, "gate": self.gate.address}
        return terms, canonical_bytes(terms), terms_hash(terms)

    def open_job(self, t_hash: str, *, expires_in: int = 3 * DAY, budget: int = PRICE, fund: bool = True) -> int:
        buyer = self.addr("buyer")
        job_id = self.chain.send(buyer, self.acp, "createJob", self.addr("provider"), self.gate.address,
                                 self.chain.timestamp + expires_in, terms_description(t_hash), self.gate.address)
        self.chain.send(buyer, self.acp, "setBudget", job_id, budget)
        if fund:
            self.chain.send(buyer, self.token, "approve", self.acp.address, budget)
            self.chain.send(buyer, self.acp, "fund", job_id, budget)
        return job_id

    def provider_accepts(self, job_id: int, terms: dict) -> list[str]:
        """Provider-side due diligence before doing the work. Returns objections (empty = accept)."""
        job = self.acp.getJob(job_id)
        problems = []
        if job["evaluator"] != self.gate.address or job["hook"] != self.gate.address:
            problems.append("evaluator/hook is not the agreed assay gate")
        if job["description"] != terms_description(terms_hash(terms)):
            problems.append("job description does not commit to the terms I was shown")
        if job["budget"] != terms["price"]["amount"] or job["status"] != "Funded":
            problems.append("escrow is not funded at the agreed price")
        margin = terms["timing"]["challenge_seconds"] + terms["timing"]["settle_margin_seconds"]
        if job["expiredAt"] <= terms["timing"]["submit_by"] + margin:
            problems.append("escrow expires too soon after the delivery deadline to settle")
        return problems

    def deliver(self, job_id: int, bundle: bytes) -> str:
        commitment = sha256_hex(bundle)
        self.chain.send(self.addr("provider"), self.acp, "submit", job_id, commitment)
        return commitment

    def relay(self, envelopes: list[dict], sender: str | None = None) -> str:
        msgs = [e["attestation"]["message"] for e in envelopes]
        sigs = [signature_tuple(e) for e in envelopes]
        return self.chain.send(sender or self.addr("relayer"), self.gate, "post", msgs, sigs)

    def balances(self) -> dict:
        who = {"buyer": self.addr("buyer"), "provider": self.addr("provider"), "escrow": self.acp.address,
               "gate": self.gate.address, "assayer": self.addr("assayer"), "treasury": self.addr("treasury")}
        return {k: self.token.balanceOf(v) for k, v in who.items()}
