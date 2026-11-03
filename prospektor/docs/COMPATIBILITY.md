# Compatibility: ERC-8183, ERC-8004, x402

Checked 2 November 2026 against the sources pinned below. All three are moving targets: ERC-8183
and ERC-8004 are **Drafts**. Labels: **prototype** = simulated and tested here; **proposal** =
designed, not built.

## Pinned sources

| Spec | Source and pin | Status / date |
|---|---|---|
| ERC-8183 Agentic Commerce | `ethereum/ERCs` @ `0da1c2b1b007d073853c89a867ebff62cae539c2`, `ERCS/erc-8183.md`, git blob `b6346637…`, sha256 `257c35bb…efa3a` | Draft, created 2026-02-25 |
| ERC-8004 Trustless Agents | same commit, `ERCS/erc-8004.md`, git blob `7653a809…`, sha256 `249dc3d9…c3f8a9` | Draft, created 2025-08-13 |
| EIP-712 typed data | `ethereum/EIPs` @ `dc5d5fa688b7…`, `EIPS/eip-712.md` and `assets/eip-712/Example.js` | Final (created 2017-09-12); its published test vector passes here |
| x402 protocol | `x402-foundation/x402` @ `5220ceba2298…` (2 Nov 2026), `specs/x402-specification-v2.md` | Protocol v2 (v2.0 dated 2025-12-09); `auth-capture` scheme present (its files were renamed 2026-05-20 and last changed 2026-10-27) |

## ERC-8183 — escrow and evaluator (prototype, simulated)

**Mapping.** PROSPEKTOR is not the evaluator key; the **AssayGate contract** is the job's
`evaluator` and `hook`. The office signs; anyone relays; the gate calls `complete(jobId, reason)`
or `reject(jobId, reason)` with `reason` = the receipt's SHA-256. HOLD → no call.

| Spec element | Prototype |
|---|---|
| Six states, eight transitions, "no other transitions are valid" | All simulated; exhaustive 120-case table (`test_escrow.TransitionTable`) |
| Role checks (client / provider / evaluator) | Simulated with msg.sender semantics |
| `fund(jobId, expectedBudget)` front-running guard | Simulated (spec mode); missing in reference mode, see below |
| Optional provider set later | Simulated |
| Hooks: before/after on hookable calls; `claimRefund` not hookable; after-hook revert rolls back | Simulated and tested |
| Platform fee on completion only | Simulated |
| `reason` attestation hash | Receipt SHA-256 (single assayer) or SHA-256 of sorted receipt hashes (quorum) |
| ABI encoding of hook data, hook gas limits, ERC-165, ERC-2771, ERC-2612, upgrades | **Not simulated** |

**Observations on the pinned document** (each reproducible in the tests; worth reporting to the
ERC-8183 discussion if the Operator authorizes external contact):

1. The embedded reference `AgenticCommerce.sol` has **no `expectedBudget` in `fund()`**, which the
   text requires as front-running protection. With a generous allowance, a provider can raise the
   budget before the buyer's `fund()` lands: the demo shows 2,500 pulled after 250 was agreed.
2. The reference **evaluator fee is paid only on `complete()`**, a standing incentive to approve.
   PROSPEKTOR's position: evaluator fee 0 on-chain; any assay fee is charged regardless of verdict.
3. **`complete()` has no expiry check**, so after `expiredAt` an evaluator decision and
   `claimRefund()` race. The gate refuses to settle at or after expiry.
4. **The job struct does not store the deliverable**; it is only in the `JobSubmitted` event. The
   gate records it through the hook so it can check attestations against it.
5. **No dispute or appeal, and no way to extend expiry.** Any unresolved HOLD or dispute ends in a
   buyer refund.
6. The reference contract is **UUPS-upgradeable with admin roles**, so escrow logic can change
   while a job is open. An evaluator cannot protect against that; buyers and providers should
   check who controls upgrades.
7. Reference `setBudget()` is provider-only (the text says client or provider), and reference
   `submit()` also accepts a zero-budget job straight from Open.

**Integration path (proposal):** port the gate to Solidity (EIP-712 + `ecrecover`, string
comparison of the description), test it with Foundry against the pinned reference contract, then
on a public testnet.

## ERC-8004 — identity, reputation, validation (proposal)

* **Identity.** Register the assay office as an agent whose registration file lists the gate
  address, the authorized assayer addresses, and the published assay specs (by hash). Providers
  check this before accepting a job; otherwise a buyer could name a look-alike gate.
* **Validation registry.** After settlement, the office can answer a provider's
  `validationRequest` with `validationResponse(requestHash, 100 or 0, receiptURI, receiptHash,
  "prospektor/roster/0")`. HOLD should not be posted as a number: 0–100 has no "undecided", and
  50 would read as partial success.
* **Selection bias.** In ERC-8004 the validated agent chooses whom to ask; in ERC-8183 the buyer
  chooses the evaluator. Readers should filter validation summaries by validator address.
* **Reputation.** Feedback belongs to the client; the office should not post reputation itself.

Not built: no registry contract, registration file or posting code exists in this prototype.

## x402 — machine payments (proposal)

* **`exact` (pay per request)** verifies and settles a payment around a single request. It proves
  payment, not delivery. Visa/Artemis figures reported in July 2026 put adjusted x402 volume near
  $19M over about 134M transactions, roughly $0.14 each by our division, so a per-request assay
  would often cost more than the payment it checks.
* **`auth-capture` with `paymentFlow: escrow`** holds funds, then the operator captures or voids;
  the client can `reclaim` after the capture deadline (the analogue of `claimRefund`). With
  `operatorType: "custom"`, a contract operator applies its own rules out of band. An AssayGate
  variant could be that operator: capture on PASS, void on FAIL, nothing on HOLD.
* **Fee rail.** The office could charge a flat, verdict-independent fee per assay through x402.
* **Offer-and-receipt extension** gives the *seller's* signed receipt: self-attestation, which
  complements a third-party assay receipt but does not replace it.

Not built: no x402 server, facilitator call or auth-capture operator exists here.

## Sources

* [ERC-8183: Agentic Commerce](https://ercs.ethereum.org/ERCS/erc-8183) and its [discussion](https://ethereum-magicians.org/t/erc-8183-agentic-commerce/27902)
* [ERC-8004: Trustless Agents](https://ercs.ethereum.org/ERCS/erc-8004)
* [x402 specification v2](https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md), [auth-capture scheme](https://github.com/x402-foundation/x402/blob/main/specs/schemes/auth-capture/scheme_auth_capture.md), [offer and receipt extension](https://github.com/x402-foundation/x402/blob/main/specs/extensions/extension-offer-and-receipt.md)
* [EIP-712](https://eips.ethereum.org/EIPS/eip-712)
* [The Defiant: Visa's Sheffield pegs adjusted x402 volume at $19M](https://thedefiant.io/news/infrastructure/visa-s-sheffield-pegs-adjusted-x402-volume-at-19m) (16 July 2026)
