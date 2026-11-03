# Decision record 0001 — PROSPEKTOR as a non-custodial ERC-8183 evaluator

Date: 2 November 2026 · Relay pass: Claude/Constraint Architect · Status: **prototype**, awaiting
Operator review. Nothing here is canon until merged.

## Context

The Operator's directive: an independent verification system for paid work between AI agents,
built as a locally testable vertical slice, that never takes custody, never releases funds on
HOLD, starts with deterministic work, and claims nothing it has not shown.

## A — Analyze: what the standards already solve

| Standard (pinned in [COMPATIBILITY.md](COMPATIBILITY.md)) | Solves | Leaves open |
|---|---|---|
| ERC-8183 Agentic Commerce (Draft, created 2026-02-25) | Escrowed job lifecycle; a single `evaluator` address decides `complete` or `reject`; refunds on expiry | How the evaluator decides, what evidence it keeps, disputes (none), expiry extension (none) |
| ERC-8004 Trustless Agents (Draft, created 2025-08-13) | Agent identity, feedback, and a validation registry where validators post 0–100 responses | Who validates and how; the validated agent chooses its own validator |
| x402 v2 (spec v2.0, 9 Dec 2025; repo checked 2 Nov 2026) | Proving a payment was authorized and settled for a web request; `auth-capture` adds a hold with capture/void by an operator | Whether the paid-for work was delivered; the operator's capture decision is out of band |

**The unsolved problem.** All three rails now have a seat for "someone decides whether the
work was delivered" (ERC-8183's evaluator, ERC-8004's validator, x402 auth-capture's custom
operator). None defines how that decision is evidenced, reproduced by a third party, kept from
paying on ambiguity, or bound to one job so it cannot be replayed. **Payment verification**
(x402's `/verify` and `/settle`: was the payment authorized, is it unspent, did it move) is
mature. **Work verification** (does this deliverable meet the agreed criteria) is the gap
PROSPEKTOR targets.

## E — Expand: verification methods compared

Ratings are qualitative judgments for this design, not measurements.

| Method | Reliability | Cost per job | Scales | Security | Independence | Commercial use |
|---|---|---|---|---|---|---|
| 1. Deterministic tests against agreed criteria | Exact for what the criteria cover | ~zero compute | Yes, per job type | Strong if inputs are pinned | Reproducible by anyone | **High** for objective work; needs a spec per job type |
| 2. Source/evidence verification (pinned by hash) | Exact for presence and integrity, not meaning | Low | Yes | Strong against swapped evidence | Reproducible | High for data and citation work |
| 3. Cryptographic deliverable commitment | Proves *which* bytes, not their quality | ~zero | Yes | Blocks bait-and-switch and griefing | Anyone can check | **Required** baseline |
| 4. Independent re-execution | Exact where the job is re-runnable | Up to the job's own cost | Limited by cost | Strong | Strong | Medium: only when checking is cheaper than doing |
| 5. Multiple independent evaluators (k-of-n) | Reduces single-key error and collusion | k × cost | Yes | Limits key theft and bias | Only if keys are truly independent | Medium: worth it for high value |
| 6. Dispute escalation and umpire review | Handles what machines cannot | Human time | Poorly | Depends on rules | Depends on who the umpire is | High value, high liability; needs legal design |

LLM judgment was considered and **not given authority**: it can inform a human umpire but
cannot make a PASS that releases funds (directive section 4).

## R — Refine: the smallest architecture that shows a real lifecycle

* **Escrow:** ERC-8183 per the pinned normative text (simulated; reference-code deviations
  reproducible in `mode="reference"`).
* **Terms binding:** the job's `description` is exactly `prospektor-terms/0 sha256:<hash>` of the
  canonical terms document, so the criteria are fixed and visible before any work starts.
* **Deliverable binding:** `submit(deliverable)` carries the SHA-256 of the exact bytes; the
  office refuses anything else (no verdict), so a third party cannot make honest work fail.
* **Evaluator = AssayGate contract** (also the job's hook, to record the deliverable): accepts
  EIP-712 attestations bound to chain, gate, escrow, job, deliverable and terms hash; PASS →
  `complete`, FAIL → `reject`; HOLD has no code path to payment; optional challenge window;
  k-of-n keys above a budget tier; no admin, no upgrade, no funds.
* **Office:** pure, versioned engine (its source hash goes into every receipt), signed receipts,
  an append-only hash-chained ledger with one terminal verdict per job.
* **HOLD = abstain.** ERC-8183 has no HOLD state; not settling is the only safe mapping.

Rejected alternatives: the office key as the escrow's evaluator (a fund-directing key that must
send transactions); an LLM judge; a new protocol. Deferred: optimistic-oracle disputes, TEE or
zero-knowledge proofs, staking.

## C — Critique: what was attacked, and what broke during this pass

Attacks tried are listed in [SECURITY.md](SECURITY.md) with the test that covers each. Five
problems were found by the tests and critique and fixed before this PR; each fix is covered:

1. **Quorum co-signatures were rejected as replays** (replay key was the digest alone). Fixed:
   keyed by digest and signer. Found by `test_high_value_needs_two_independent_keys`.
2. **Liveness: a PASS not relayed within its 1-hour validity window could never be renewed**, so
   good work became unpayable and the buyer was refunded at expiry. Found by the lifecycle random
   walk. Fixed: the office re-issues the same verdict with a fresh window and never signs the
   opposite verdict (a disagreement becomes HOLD `office.consistency`).
3. **Identifier regex accepted a trailing newline** (`$` in Python). Fixed with `fullmatch`.
4. **A broken `cryptography` build panics on import** (BaseException, not ImportError) on one
   interpreter. Fixed: the independent checker falls back to the `openssl` command.
5. **ERC-8183 `complete()` has no expiry check**, so a late evaluator decision races
   `claimRefund()`. The gate refuses to settle at or after `expiredAt`.

The test suite was also checked for teeth: each of the nine machine-checkable rules was disabled
in turn, and an independent answer key caught every one (`TheTestsHaveTeeth`). One fixture was
rebuilt when that test showed a case violating two rules at once.

**Lessons carried forward from an earlier offline prototype review** (inherited, not re-run in
this pass; that prototype is not in this repository):

| Lesson | Here |
|---|---|
| Office-side faults must not fail the seller | Missing/corrupt input, crashed check, clock or setup problems → HOLD (`OfficeFaultsHoldNotFail`, `HoldTests`) |
| Freshness and deadlines must not rest on provider-claimed dates | Chain-stamped submission time; attestations expire (`test_late_delivery_uses_chain_time_not_a_claimed_time`) |
| Receipts must bind the escrow | Chain id, escrow, gate, job, deliverable, terms, budget, token, engine hash (`test_any_edit_is_detected`) |
| Concurrent requests or a restart must not release twice | Escrow state machine + durable ledger lock (`test_concurrent_*`, `test_idempotent_and_restart_safe`) |
| No process-local sequential tokens | Content-addressed receipts; jobs identified by escrow and job id |

## S — Synthesize: decision

Adopt this design as the prototype baseline: deterministic assay specs per job type, a
non-custodial evaluator gate on ERC-8183, signed receipts anyone can verify, HOLD as abstention.

**Consequences.** Works today only for objective job types. Inherits ERC-8183's refund-on-expiry
default, which favors buyers in every unresolved case. Commercial value depends on being a
trusted, independent operator, not on the code, which is public.

**Next technical step (proposal):** port AssayGate to Solidity and run it on a local EVM against
the reference contract, with the same Python receipts as input; then have someone who did not
build it review and run the tests.
