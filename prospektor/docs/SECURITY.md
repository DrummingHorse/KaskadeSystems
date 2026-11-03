# Security notes: how a bad actor might get paid for invalid work

Scope: the prototype in this folder (simulation, unaudited, test keys). "Blocked" means a test or
the recorded demo shows the attack failing in the simulation. It does not mean production-safe.

## Threats, defenses and the evidence for each

| # | Attack | Defense | Shown by | Status |
|---|---|---|---|---|
| T1 | Submit one commitment, send the office different (better) bytes | Office assays only bytes whose SHA-256 equals the on-chain `deliverable`; otherwise no verdict | `Intake`, demo A7 | Blocked |
| T2 | Send the office bad bytes for someone else's job, to make honest work FAIL | Same rule: mismatched bytes get no verdict | `test_only_the_committed_bytes_...` | Blocked |
| T3 | Deliver invalid work | Deterministic checks against pinned terms; streak test rejects malformed work before fire assay | `RuleTests`; 1,388 invalid mutations all FAIL; demo job 2 | Blocked |
| T4 | Cite records that do not exist, or alter the pinned input | References must resolve in the pinned input; input hash must match terms (mismatch is HOLD) | `test_unknown_references`, `test_missing_or_wrong_pinned_input` | Blocked |
| T5 | Prompt injection in the deliverable | No check interprets free text; no model in the loop | `InjectionTests`; demo job 2 | Blocked |
| T6 | Call `complete()` or `reject()` directly, or claw back funded escrow | ERC-8183 role checks | 120-case `TransitionTable`; demo A1, A6 | Blocked |
| T7 | Sign a PASS with any other key | Gate accepts only listed assayer keys | demo A2; random walk forgeries | Blocked |
| T8 | Edit a field of a real attestation (verdict, times, receipt hash) | Every field is inside the EIP-712 signature | `test_every_field_is_bound_by_the_signature`; demo A3 | Blocked |
| T9 | Replay a PASS on another job, chain or gate, even with identical bytes and terms | Domain binds chain and gate; message binds escrow, job, deliverable, terms | `test_replay_onto_identical_job_...`, `test_other_chain_or_gate_...`; demo A4 | Blocked |
| T10 | Get paid twice: re-post, race relays, restart the office | Escrow state machine; serialized transactions; ledger lock with one terminal verdict per job | `test_concurrent_relays_...`, `Durability`; demo A5 | Blocked |
| T11 | Make the office sign PASS after FAIL (or the reverse) | Re-assay may only re-issue the same verdict; a disagreement becomes HOLD | `test_never_signs_the_opposite_verdict` | Blocked |
| T12 | Settle a HOLD | Gate has no path from HOLD to payment | `test_hold_and_unknown_verdicts_cannot_settle`; demo job 3 | Blocked |
| T13 | Manipulate payment conditions (raise the budget before funding) | Spec `fund(expectedBudget)`; office HOLDs any budget or token that differs from terms | `test_front_running_budget_is_blocked`, `test_payment_differs_from_agreed_price` | Blocked in spec mode; **possible against the ERC's reference code** |
| T14 | Timing games: late delivery, delivery too close to expiry, stale or post-expiry decisions | Chain-stamped submission time; settle-window intake check; attestation validity window; gate refuses after expiry | `test_late_delivery_...`, `test_too_late_to_settle`, `test_stale_and_late_attestations`; demo A8 | Blocked |
| T15 | Contradictory findings, or one key counted twice | Quorum requires distinct keys and one verdict | `Quorum` tests | Blocked |
| T16 | Office faults (crash, missing input, bad clock) used to fail a seller | Every office-side fault is HOLD | `HoldTests`, `OfficeFaultsHoldNotFail` | Blocked |
| T17 | Rewrite history: edit, delete, reorder receipts | Hash chain + signatures; settled receipts anchored as on-chain `reason` | `Receipts` tests; demo A9; independent checker | Detected |
| T18 | Call the gate's hook entry points directly to overwrite a deliverable | Hooks accept calls from the escrow contract only | `test_hook_entry_points_are_escrow_only` | Blocked |
| T19 | Signature malleability, parser differentials (duplicate keys, NaN, floats, deep nesting, BOM, trailing newline) | Low-s only; strict canonical parsing; full-match identifiers | `test_high_s_twin_...`, `StrictJSONTests` | Blocked |
| T20 | Evaluator bias from fees paid only on approval | Evaluator fee 0 on-chain; fee charged whatever the verdict (policy) | `test_evaluator_fee_pays_only_on_approval` shows the reference incentive | Policy, not enforced by code |

## Unresolved risks (not fixed in this pass)

* **R-1 Key compromise or collusion at the single-key tier.** A stolen assayer key can sign PASS
  for bad work on any job below the quorum threshold. Needs: hardware-held keys, per-key value
  caps, rotation and revocation (the gate is immutable, so a compromised gate must be replaced and
  open jobs are stuck with it), and genuinely independent second assayers.
* **R-2 Disputes are a free refund option.** ERC-8183 cannot extend expiry and has no appeal, so a
  disputed or held job always refunds the buyer. A buyer can dispute good work and, if the work was
  visible, keep it. Needs dispute bonds, an umpire with binding rules, and legal review before
  anything is offered.
* **R-3 Deliverable confidentiality.** The office sees the work before payment. Receipts carry
  hashes, not content, but nothing yet stops the content leaking to the buyer before settlement.
* **R-4 Providers bear the HOLD default.** Any subjective criterion means no payment unless a human
  resolves it before expiry.
* **R-5 Escrow upgradeability.** The reference escrow is upgradeable by its admin; no evaluator can
  defend against a changed escrow.
* **R-6 Simulation gap.** No real EVM, no transaction signatures, gas, ABI encoding or reorgs.
  The gate exists only as Python. Its Solidity port and audit are future work.
* **R-7 Prototype cryptography.** Pure-Python secp256k1 and Keccak, not constant-time. Never use
  them with keys that protect value.
* **R-8 Regulatory.** An evaluator that directs releases of other people's crypto-assets may raise
  money-transmission or virtual-currency questions, including under New York rules. Not legal
  advice: get a lawyer's read before any real-funds pilot.

## Can the verifier itself be independently tested?

Yes, and this pass does it six ways:

1. **Published vectors:** the EIP-712 spec's own vector (digest and signature) is reproduced
   byte-for-byte; Keccak matches published vectors.
2. **Independent implementations:** the Keccak permutation is checked against `hashlib.sha3_256`
   on 320 inputs; signatures verify in OpenSSL via `cryptography` and via the `openssl` command.
3. **Independent answer key:** a separately written validity function agrees with the engine on
   3,001 generated rosters (1,500 mutations, 1,500 random rosters, plus the good roster), and every
   invalid one is FAIL.
4. **Tests with teeth:** disabling any one of the nine machine-checkable rules is caught by that
   answer key.
5. **Independent receipt checker:** `tools/verify_receipts.py` shares no code with the package.
6. **Reproducibility:** the engine's source hash is in every receipt, and the recorded run is
   byte-identical on Python 3.11, 3.12 and 3.13.

What this does not establish: correctness of the *criteria* (they encode what the buyer asked
for, not what the buyer needed), behaviour on a real chain, or resistance to an attacker with
access to the office's machine.
