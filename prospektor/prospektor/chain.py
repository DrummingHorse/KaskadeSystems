"""A small in-process chain simulation: accounts, atomic transactions, events.

Prototype. This is NOT a blockchain and moves no real value. It gives the
ERC-8183 simulation the properties the lifecycle depends on:

* every transaction is atomic: a revert rolls back all contract storage
  and events written during it, including nested contract calls;
* msg.sender is the transaction sender, or the calling contract for
  nested calls, so role checks behave as they would on-chain;
* transactions are serialized (one at a time), like blocks;
* time only moves when the simulation advances it.

Limitation: externally owned accounts are not authenticated. The caller
of `send` names the sender; a real chain would require a transaction
signature. Assay attestations, by contrast, are real ECDSA signatures
verified by the gate.
"""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field

from .keccak import keccak256
from .secp256k1 import to_checksum_address

ZERO = "0x0000000000000000000000000000000000000000"
UINT256_MAX = (1 << 256) - 1


class Revert(Exception):
    """A reverted transaction. The message is the revert reason."""


def same_address(a: str, b: str) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower()


def require_address(a) -> str:
    if not (isinstance(a, str) and a.startswith("0x") and len(a) == 42):
        raise Revert("InvalidAddress")
    try:
        bytes.fromhex(a[2:])
    except ValueError:
        raise Revert("InvalidAddress") from None
    return to_checksum_address(bytes.fromhex(a[2:]))


@dataclass(frozen=True)
class Event:
    block: int
    timestamp: int
    tx: int
    contract: str
    name: str
    args: dict

    def as_dict(self) -> dict:
        return {"block": self.block, "timestamp": self.timestamp, "tx": self.tx,
                "contract": self.contract, "event": self.name, "args": self.args}


@dataclass
class TxRecord:
    tx: int
    block: int
    timestamp: int
    sender: str
    contract: str
    function: str
    status: str
    revert_reason: str | None = None

    def as_dict(self) -> dict:
        return {"tx": self.tx, "block": self.block, "timestamp": self.timestamp, "from": self.sender,
                "to": self.contract, "function": self.function, "status": self.status,
                "revert": self.revert_reason}


class Contract:
    """Base class. Contract state lives only in self.s, so the chain can snapshot it."""

    def __init__(self, chain: "Chain", address: str):
        self.chain = chain
        self.address = address
        self.s: dict = {}

    @property
    def msg_sender(self) -> str:
        return self.chain._sender_stack[-1]

    @property
    def now(self) -> int:
        return self.chain.timestamp

    def emit(self, name: str, **args) -> None:
        self.chain._emit(self.address, name, args)

    def call(self, target: "Contract", fn: str, *args, **kwargs):
        """Nested call; msg.sender becomes this contract."""
        return self.chain._invoke(self.address, target, fn, args, kwargs)


@dataclass
class Chain:
    chain_id: int = 31337
    timestamp: int = 1_800_000_000
    block: int = 1
    contracts: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    txs: list = field(default_factory=list)

    def __post_init__(self):
        self._lock = threading.RLock()
        self._sender_stack: list[str] = []
        self._deploy_nonce = 0
        self._tx_counter = 0
        self._current_tx = 0

    # -- deployment and time ------------------------------------------------
    def deploy(self, cls, deployer: str, *args, **kwargs):
        with self._lock:
            self._deploy_nonce += 1
            raw = keccak256(f"prospektor-sim-deploy/{deployer.lower()}/{self._deploy_nonce}".encode())[-20:]
            address = to_checksum_address(raw)
            contract = cls(self, address, *args, **kwargs)
            self.contracts[address] = contract
            return contract

    def advance(self, seconds: int) -> None:
        if seconds < 0:
            raise ValueError("time cannot move backwards")
        with self._lock:
            self.timestamp += seconds
            self.block += 1

    # -- transactions -------------------------------------------------------
    def send(self, sender: str, target: Contract, fn: str, *args, **kwargs):
        """Execute one atomic transaction. Raises Revert after rolling back."""
        with self._lock:
            sender = require_address(sender)
            self._tx_counter += 1
            self._current_tx = self._tx_counter
            snapshot = {addr: copy.deepcopy(c.s) for addr, c in self.contracts.items()}
            n_events = len(self.events)
            rec = TxRecord(self._current_tx, self.block, self.timestamp, sender, target.address, fn, "ok")
            try:
                result = self._invoke(sender, target, fn, args, kwargs)
            except Revert as exc:
                for addr, state in snapshot.items():
                    self.contracts[addr].s = state
                del self.events[n_events:]
                rec.status, rec.revert_reason = "reverted", str(exc)
                self.txs.append(rec)
                raise
            except Exception as exc:  # a bug in a simulated contract must not half-apply
                for addr, state in snapshot.items():
                    self.contracts[addr].s = state
                del self.events[n_events:]
                rec.status, rec.revert_reason = "reverted", f"InternalError:{type(exc).__name__}"
                self.txs.append(rec)
                raise Revert(f"InternalError:{type(exc).__name__}: {exc}") from exc
            self.txs.append(rec)
            self.block += 1
            return result

    def _invoke(self, sender: str, target: Contract, fn: str, args, kwargs):
        if fn.startswith("_") or not callable(getattr(target, fn, None)):
            raise Revert(f"NoSuchFunction:{fn}")
        self._sender_stack.append(sender)
        try:
            return getattr(target, fn)(*args, **kwargs)
        finally:
            self._sender_stack.pop()

    def _emit(self, contract: str, name: str, args: dict) -> None:
        self.events.append(Event(self.block, self.timestamp, self._current_tx, contract, name, dict(args)))

    def events_of(self, contract: Contract | str, name: str | None = None, **match) -> list[Event]:
        addr = contract if isinstance(contract, str) else contract.address
        out = []
        for ev in self.events:
            if not same_address(ev.contract, addr) or (name and ev.name != name):
                continue
            if all(ev.args.get(k) == v for k, v in match.items()):
                out.append(ev)
        return out


class TestToken(Contract):
    """Minimal ERC-20 for local tests. It has no value and exists only in this process."""

    name = "Test USD (no value, simulation only)"
    symbol = "tUSD"
    decimals = 6

    def __init__(self, chain, address, minter: str):
        super().__init__(chain, address)
        self.s.update(minter=minter, balances={}, allowances={}, total_supply=0)

    def balanceOf(self, account: str) -> int:
        return self.s["balances"].get(account.lower(), 0)

    def allowance(self, owner: str, spender: str) -> int:
        return self.s["allowances"].get(f"{owner.lower()}:{spender.lower()}", 0)

    def totalSupply(self) -> int:
        return self.s["total_supply"]

    def mint(self, to: str, amount: int) -> None:
        if not same_address(self.msg_sender, self.s["minter"]):
            raise Revert("OnlyMinter")
        self._check_amount(amount)
        self.s["balances"][to.lower()] = self.balanceOf(to) + amount
        self.s["total_supply"] += amount
        self.emit("Transfer", **{"from": ZERO, "to": to, "value": amount})

    def approve(self, spender: str, amount: int) -> bool:
        self._check_amount(amount)
        self.s["allowances"][f"{self.msg_sender.lower()}:{spender.lower()}"] = amount
        self.emit("Approval", owner=self.msg_sender, spender=spender, value=amount)
        return True

    def transfer(self, to: str, amount: int) -> bool:
        self._move(self.msg_sender, to, amount)
        return True

    def transferFrom(self, owner: str, to: str, amount: int) -> bool:
        spender = self.msg_sender
        allowed = self.allowance(owner, spender)
        if allowed < amount:
            raise Revert("ERC20InsufficientAllowance")
        if allowed != UINT256_MAX:
            self.s["allowances"][f"{owner.lower()}:{spender.lower()}"] = allowed - amount
        self._move(owner, to, amount)
        return True

    def _move(self, frm: str, to: str, amount: int) -> None:
        self._check_amount(amount)
        if same_address(to, ZERO):
            raise Revert("ERC20InvalidReceiver")
        bal = self.balanceOf(frm)
        if bal < amount:
            raise Revert("ERC20InsufficientBalance")
        self.s["balances"][frm.lower()] = bal - amount
        self.s["balances"][to.lower()] = self.balanceOf(to) + amount
        self.emit("Transfer", **{"from": frm, "to": to, "value": amount})

    @staticmethod
    def _check_amount(amount) -> None:
        if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= UINT256_MAX:
            raise Revert("InvalidAmount")
