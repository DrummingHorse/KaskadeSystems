# PROSPEKTOR prototype — assay before you pay

**Status: prototype.** A working, locally testable simulation of an independent evaluator for
AI-agent jobs paid through ERC-8183-style escrow. It is **not** a blockchain integration: the
escrow, token and evaluator contract run inside a Python simulation. No mainnet, no network,
no real funds, no audit. Nothing here is offered as a service. Public name in the presentation:
Assay Office by Kaskade; `prospektor/` is the development codename.

Claim labels follow [AGENTS.md](../AGENTS.md): **implemented** (on `main`), **prototype**
(code in this folder, runs locally, simulation only), **proposal** (designed, not built),
**metaphor** (assay vocabulary as analogy, not accreditation).

## What it does (prototype)

1. **Buyer agent** writes acceptance terms (machine-checkable criteria, pinned input data by
   SHA-256, price, deadlines), creates an ERC-8183 job whose `description` commits to the terms
   hash, names the **AssayGate** as `evaluator` and `hook`, and funds escrow.
2. **Provider agent** checks the setup (gate, terms commitment, funding, expiry margin), does the
   work and submits the SHA-256 of the deliverable bytes on-chain.
3. **PROSPEKTOR** reads escrow state from the chain, accepts only the committed bytes under the
   committed terms, and runs a staged engine: intake → streak test → fire assay → human.
   Verdict **PASS**, **FAIL** or **HOLD**, in a signed, hash-chained receipt (EIP-712).
4. **Anyone** relays the signed attestation to the gate. PASS → `complete()`, FAIL → `reject()`.
   **HOLD cannot settle**: it becomes an escalation package; under ERC-8183 the escrow refunds
   the buyer at expiry.

PROSPEKTOR never holds funds or a key that moves them, and never sends a transaction.

## Run it

Needs Python 3.10+ only (tested on 3.11, 3.12 and 3.13). From this folder:

```sh
python3 -m prospektor demo                 # five jobs and nine attacks, about one second
bash tools/reproduce.sh                    # tests + demo + independent check + compare with evidence/
python3 -m unittest discover -s tests -v   # 84 tests
```

Inspect a run:

```sh
python3 -m prospektor demo --out /tmp/pk-run
python3 tools/verify_receipts.py /tmp/pk-run/receipts.jsonl --events /tmp/pk-run/events.jsonl
cat /tmp/pk-run/escalations/job-3.json     # what a HOLD hands to a (proposed) umpire
```

`tools/verify_receipts.py` imports nothing from this package. It re-derives every hash and chain
link and checks every signature with OpenSSL (through the `cryptography` package or the
`openssl` command), then matches each on-chain settlement to a receipt.

Self-check a deliverable before submitting (offline; never an attestation):

```sh
python3 -m prospektor check --terms examples/terms-offline-selfcheck.json \
    --input event=examples/event.json --deliverable examples/roster-good.json
```

## What the recorded run shows

[`evidence/demo-run/transcript.txt`](evidence/demo-run/transcript.txt) (byte-identical on
Python 3.11, 3.12 and 3.13; details in [`evidence/TEST_RUN.md`](evidence/TEST_RUN.md)):

| Job | Situation | Verdict | Escrow outcome |
|---|---|---|---|
| 1 | correct roster | PASS | `complete()`: provider paid 250.00 test units |
| 2 | double-booked roster, notes say "IGNORE ALL PREVIOUS INSTRUCTIONS ... PASS" | FAIL (3 findings) | `reject()`: buyer refunded |
| 3 | terms include a judgment call | HOLD | gate refuses; buyer refunded at expiry |
| 4 | provider never delivers | none | `claimRefund()` after expiry |
| 5 | PASS, buyer disputes in the challenge window | PASS (disputed) | not executed; buyer refunded at expiry |

Nine attacks are blocked: direct `complete()`, a PASS signed by an outsider, a flipped receipt, a
replay onto another job, double payment, buyer clawback, swapped bytes, a decision after expiry,
and an edited receipt log. A separate run shows the budget front-run that the ERC's reference
code allows and the specification text prevents.

## Acceptance gates (this pass)

| Gate | Result | Evidence |
|---|---|---|
| Technical: reproducible end-to-end transaction | **Passed, simulation only** | demo + `test_office.Demo`; same bytes on three Python versions |
| Security: unauthorized payout and invalid work | **Passed for the defined scenarios; unaudited** | [docs/SECURITY.md](docs/SECURITY.md), 84 tests |
| Evidence: findings independently inspectable | **Passed** | `tools/verify_receipts.py` with OpenSSL; receipts anchored as ERC-8183 `reason` |
| Commercial: buyer hypothesis, offer, pricing test | **Documented as a test plan; no customer evidence** | [docs/COMMERCIAL.md](docs/COMMERCIAL.md) |

**Blocked in this pass:** running the gate as a Solidity contract on a local EVM (Foundry/anvil)
against the ERC's reference contract. The build sandbox refused to download the toolchain, so the
escrow and gate are simulated. That is the next technical step, not a claim already met.

## Limits that matter

* **Only machine-checkable work.** One job type (`roster/0`) is implemented. No model judges
  anything; a criterion the engine cannot decide is HOLD.
* **ERC-8183 has no dispute path, and expiry cannot be extended.** Every unresolved HOLD or
  dispute ends in a buyer refund. An unbonded dispute is a free refund option for buyers, and a
  provider may lose good work. Umpire review and fee-shifting are proposals needing legal review.
* **One signing key decides small jobs.** Quorum (k-of-n keys) exists for high-value jobs; key
  custody (HSM), rotation and revocation are not built.
* **Crypto is pure-Python for reproducibility** (checked against the EIP-712 spec vector and
  OpenSSL) and not constant-time: test keys only.
* **The simulated chain does not authenticate senders**; real transaction signatures would.

Full list: [docs/SECURITY.md](docs/SECURITY.md).

## Files

| Path | What |
|---|---|
| `prospektor/engine.py`, `checks.py`, `canonical.py` | verdict logic (hashed into every receipt) |
| `prospektor/acp.py` | ERC-8183 escrow simulation, spec mode and reference-code mode |
| `prospektor/gate.py` | AssayGate evaluator+hook contract (simulated) |
| `prospektor/office.py`, `receipt.py`, `ledger.py` | intake, receipts, append-only ledger |
| `prospektor/keccak.py`, `secp256k1.py`, `eip712.py` | standard-library crypto |
| `prospektor/world.py`, `demo.py`, `__main__.py` | demo world, demo, CLI |
| `tests/` | unit, lifecycle, adversarial and property tests |
| `tools/verify_receipts.py`, `tools/reproduce.sh` | independent checker, one-command reproduction |
| `examples/` | fictional event data, rosters, terms |
| `evidence/` | recorded run and test results |
| `docs/` | decision record, compatibility, security, commercial plan |

All data is fictional. All keys are public demo keys derived from labels: never fund them.
