# Commercial validation plan

Status: **proposal**. No customer has been contacted, no money spent, nothing advertised. Every
number below is either sourced (see Sources) or an explicitly labeled assumption. There is no
revenue forecast.

## Bottom line

Payment rails for agents now have a seat for an independent decision-maker, but the money in
that seat is small today and competitors already sell automated checks for cents. The paid
wedge is probably not the per-check fee. It is **writing assay specs per job type** (turning "did
they deliver?" into deterministic checks) and, later, **human umpire work**, sold to people who
need a neutral party because "evaluator = client" is unacceptable to the seller. The code is now
public; the asset is a trusted, independent operator with a library of specs and a track record.

## Who needs independent work verification, and who does it today

| Segment | Pain | Who verifies today |
|---|---|---|
| Agents **selling** objective work as escrowed jobs (data cleaning, extraction with sources, schedules and plans with hard constraints, code against a supplied test suite) | Buyers won't prepay a stranger; ERC-8183's default `evaluator = client` lets the buyer reject good work and take a refund | The buyer, or nobody |
| Agent **buyers** (operators deploying agents that hire agents) | Paying for work nobody checked | The buyer itself, often by eye or with another model |
| Agent **marketplaces** (Virtuals ACP, ClawWork-style boards) | Disputes, fraud, reputation that can be gamed | Built-in evaluator agents or rules chosen by the platform |
| **Payment gateways** for x402 | Pay-per-request settles before anyone checks quality | Seller's own signed receipt; a few verify-before-release gateways |

## Competitors and adjacent offers (as of 2 Nov 2026)

| Offer | What it does | Verification | Holds funds? | Public price |
|---|---|---|---|---|
| Virtuals ACP evaluator phase | Evaluator step in each ACP job; results feed reputation | Evaluator agent chosen per job | Escrow in protocol | Not found |
| ClawWork `erc8183-reference` | Open-source ERC-8183 contracts, SDKs and an evaluator service; says 20,000+ agents | Rule-based reviewer to be replaced by the operator's logic | Escrow contract | Open source |
| Settld | Verify-before-release gateway for x402 | Deterministic checks; green/amber/red; releases if unchallenged | Yes (escrow holds) | Not found |
| ThoughtProof | Verification APIs registered under ERC-8004, paid per call over x402 | Two opposing LLMs | No | About $0.02 per reasoning check |
| VCAP (SwarmSync.AI) | IETF individual draft for verified agent commerce | Verifier callback with signed proof; timeouts go to manual review | Marketplace holds escrow | Not found |
| Demsys agent-settlement-protocol | ERC-8183-style settlement on Base Sepolia (testnet) | Evaluator role; staking proposed, later not required | Escrow contract | Moved to a fixed per-evaluation fee for small jobs (amount not found) |
| Client as evaluator (status quo) | ERC-8183 allows `evaluator = client` | Buyer decides | — | Free |

**Where PROSPEKTOR differs:** deterministic and reproducible (anyone can re-run the receipt), HOLD
instead of guessing, never custodial, fee independent of the verdict, receipts that a third party
verifies with OpenSSL. **Where it is weaker:** only objective job types, no dispute resolution yet,
one operator, no track record, demand unproven.

## What a buyer would pay, and can inspection cost more than the job?

Market anchors (sourced): adjusted x402 volume near **$19M over about 134M transactions** (Visa and
Artemis, reported 16 July 2026), about **$0.14 per transaction** by our division, with about 4,000
wallets making about 90% of adjusted spend. ThoughtProof charges about **$0.02** per automated
reasoning check. An x402 operator running 124 endpoints commented that verification latency is not
worth it for $0.001–$0.01 calls but is for tasks over $1 (one anecdote).

Assumptions used below (none are measured market data):

* **A1** Marginal cost of one automated assay is under $0.01: the recorded demo runs five jobs in
  about a second of CPU in pure Python, with no model calls.
* **A2** Writing a new assay spec (criteria, checks, fixtures, tests) takes 4–16 skilled hours.
* **A3** Settling through the gate on a low-fee chain costs cents (not measured; simulation only).
* **A4** Buyers accept up to about 2% of job value for payment protection.
* **A5** A human umpire review takes 0.5–2 hours.

Consequences:

* Per-request x402 payments cannot carry an assay: even $0.01 is about 7% of an average payment.
  **Target escrowed jobs, not API calls.**
* Under A4, a flat $0.25 automated assay fits jobs of $12.50 and up (0.25 / 0.02).
* Under A5 and a $75/hour umpire rate (assumption), a review costs $37.50–$150. Under A4 that only
  fits jobs of roughly $1,900–$7,500 unless the losing party pays a bond, which needs legal design.
* Setup is the real cost: under A2 a spec costs 4–16 hours, so per-check fees alone recover it only
  at volume (for example, at $0.25 per assay, 2,000 assays to recover a $500 spec).

**Fee-per-transaction API:** technically ready (one call per assay; x402 could carry the fee), but
at cents per check and today's volumes it is a channel, not the business.

## Fee structures to test (assumptions, not prices)

| Option | Shape | Note |
|---|---|---|
| F1 | Flat fee per automated assay, same for PASS, FAIL or HOLD | Removes the approve-to-get-paid bias |
| F2 | One-time assay-spec fee per job type | **Testable now with tiny volume** |
| F3 | Monthly fee for hosting a gate and maintaining specs | After F2 has buyers |
| F4 | Umpire review per dispute, losing side pays | Blocked: dispute rules, bonds, legal review |
| Avoid | Completion-only fees, holding funds, a token | Bias, custody, regulatory risk |

## Buyer hypothesis

**H1.** Builders who sell machine-checkable agent work as escrowed jobs of about $10 or more
(ERC-8183 jobs or x402 escrow-flow payments) will pay a one-time fee for a neutral assay spec and
evaluator gate for one job type, because it lets buyers fund escrow without trusting the seller,
and lets the seller avoid `evaluator = client`.

## First experiment: founding assay-spec pilot (proposal; needs your authorization)

* **Offer.** For one job type the builder sells, write the assay spec (deterministic criteria,
  pinned inputs, fixtures), run it on a testnet gate for 30 days on up to 100 of their test jobs,
  and hand over signed receipts any third party can verify. **$149 up front** (the price under
  test), refunded in full if fewer than three of their criteria can be machine-checked. Testnet
  only; no custody; fee the same whatever the verdict.
* **Who.** 20 builders, picked by you from public sources: ERC-8183 implementers active in the
  discussion thread, ERC-8004-registered agents selling job-style services, and x402 sellers whose
  services are priced at $1 or more. Personal messages, no ads, over two weeks.
* **Success.** At least **2 paid** within 21 days of first contact.
* **Stop or redirect.** No payment and fewer than 3 substantive replies: H1 is wrong. Next, test
  the marketplace or buyer-side hypothesis, or fold this lane into the human-reviewed report pilot.
* **Also record:** which job types are asked for, how many want subjective criteria (demand for an
  umpire), price objections, and who needs mainnet.
* **Cost.** No cash beyond payment fees. About 10–15 hours of your time if two buyers pay
  (outreach plus two specs). Obligation: deliver two specs within two weeks.
* **Why this measures willingness to pay:** money moves before the work, and the refund rule is
  narrow and objective. Replies and likes are recorded but do not count.

Cheaper alternative (also needs authorization, because it is public): post observations 1 and 3
from [COMPATIBILITY.md](COMPATIBILITY.md) to the ERC-8183 discussion with a link to this prototype,
and count inbound requests over 30 days. It builds credibility but measures interest, not payment.

## Evidence needed before any real-funds pilot

1. At least two paying spec customers.
2. The gate ported to Solidity, tested against the pinned reference contract on a local EVM, then
   reviewed and run by someone who did not build it.
3. Key custody: hardware-held keys, per-job value caps, quorum above a threshold.
4. A dispute policy (accept refund-on-expiry, or bonded umpire review) and a lawyer's read on
   virtual-currency and money-transmission questions, including New York's.
5. Written pilot terms: no custody, verdict-independent fee, liability cap.

The same signed receipt can be issued for the human-reviewed reports already proposed on the
site, so report work can build the track record this lane needs.

## Sources

* [The Defiant: Visa's Sheffield pegs adjusted x402 volume at $19M](https://thedefiant.io/news/infrastructure/visa-s-sheffield-pegs-adjusted-x402-volume-at-19m) (16 July 2026)
* [Forkast: The machine as buyer — Virtuals ACP and the evaluator problem](https://forkast.news/the-machine-as-buyer-virtuals-acp-and-the-evaluator-problem/) (22 July 2026)
* [SKALE: ThoughtProof launches on SKALE](https://skale.space/blog/thoughtproof-launches-on-skale-bringing-independent-verification-infrastructure-for-ai-agents) (16 June 2026)
* [Show HN: Verify-before-release x402 gateway (Settld)](https://hn.svelte.dev/item/47011510)
* [draft-stone-vcap-02 (IETF individual draft)](https://datatracker.ietf.org/doc/draft-stone-vcap/02/) (4 September 2026)
* [erc8183/erc8183-reference (ClawWork)](https://github.com/erc8183/erc8183-reference)
* [ERC-8183 discussion thread](https://ethereum-magicians.org/t/erc-8183-agentic-commerce/27902) (Demsys evaluator posts, May 2026)
* [Tiger Research: Virtuals Protocol ACP](https://reports.tiger-research.com/p/virtuals-protocol-acp-eng) (8 July 2025; partly funded by Virtuals)
