# Test and verification record

Relay pass: Claude/Constraint Architect, 2 November 2026. Environment: Linux sandbox (kernel 6.18),
CPython 3.11.18, 3.12.3 and 3.13.18, OpenSSL 3.0.13, `cryptography` 50.0.1. No network was used
by any of these commands. Everything here is **simulation**; nothing touched a blockchain.

## Own runs (executed in this pass, from the `prospektor/` folder)

### 1. Test suite on three Python versions

```
python3.13 -m unittest discover -s tests -p "test_*.py" -v   ->  Ran 84 tests in 16.8s  OK
python3.12 -m unittest discover -s tests -p "test_*.py"      ->  Ran 84 tests in 17.9s  OK
python3.11 -m unittest discover -s tests -p "test_*.py"      ->  Ran 84 tests in 15.1s  OK (skipped=1)
```

The skip on 3.11: that interpreter's system `cryptography` build panics on import, so the
`cryptography` cross-check is skipped there; the `openssl` command cross-check still runs.

| Module | Tests | Covers |
|---|---|---|
| `test_crypto` | 10 | Keccak vectors and SHA3 cross-check (320 inputs); EIP-712 spec vector incl. signature; EIP-55; sign/recover; malleability; OpenSSL verification two ways |
| `test_engine` | 21 | strict JSON refusals; each rule fails its own violation; format rejection skips fire assay; HOLD for manual, unknown, crashed, invalid-param and input problems; FAIL outranks HOLD; prompt injection |
| `test_escrow` | 15 | exhaustive 120-case ERC-8183 transition table; refund rules; fund guards; front-running; fees; hooks, rollback, reentrancy; reference-code deviations |
| `test_gate` | 16 | PASS/FAIL settle; every signed field bound; replay across job, chain and gate; HOLD and bad verdicts; high-s; stale/late; unwired job; hook guard; 8 concurrent relays settle once; quorum; challenge window |
| `test_office` | 15 | intake refusals; office faults HOLD; chain-time lateness FAILs; idempotency, restart, concurrency; re-issue of lapsed verdicts; no verdict flips; tamper detection; demo determinism plus independent check |
| `test_properties` | 7 | independent answer key on generated rosters; garbage input; rule-disabling check; 300-step random lifecycle walk with money and authority invariants |

Seeded statistics (`PK_STATS=1 python3 -m unittest discover -s tests -p test_properties.py`):

```
[stats] mutations: 112 valid, 1388 invalid; engine agreed with the key on all
[stats] random rosters: 2 valid, 1498 invalid; engine agreed with the key on all
[stats] random walk: 300 steps, 38 jobs {'Completed': 2, 'Funded': 12, 'Open': 5, 'Rejected': 1, 'Submitted': 18}, 322 txs (151 reverted), 2 paid, all after PASS
```

### 2. Recorded demo

```
python3 -m prospektor demo --out evidence/demo-run --quiet    ->  exit 0, "RESULT: all expectations met"
```

Output: [`demo-run/transcript.txt`](demo-run/transcript.txt), `summary.json`, `receipts.jsonl`
(5 signed receipts), `events.jsonl`, `transactions.jsonl`, `escalations/job-3.json`, `job-5.json`.

### 3. Same bytes on every interpreter

```
receipts.jsonl      963a640d0ca0d408c2cacf5366579a842302395eda6fce42efd0baa5d17c66e1
events.jsonl        95e5f7d3552e511cd61fd561e6a0a6a2591753771de487137a19e4dcf7a9aaa2
transactions.jsonl  622465e01ab1ba7b5fb923b13bc90a92c5009404b5851ff062abeaf44294d8e4
```

Python 3.11.18, 3.12.3 and 3.13.18 each produced these three files byte-identical to the
recorded run.

### 4. Independent receipt check (shares no code with the package)

```
python3 tools/verify_receipts.py evidence/demo-run/receipts.jsonl \
    --events evidence/demo-run/events.jsonl --assayer 0x462f67F977a03dB1933537d273121D2EF3f0Ded1
5 receipts checked; signatures via cryptography/OpenSSL; 2 on-chain settlements matched to receipts
RESULT: verified

(same command with the cryptography package hidden)
5 receipts checked; signatures via openssl pkeyutl; 2 on-chain settlements matched to receipts
RESULT: verified
```

A copy with one verdict edited fails with "body does not hash to receipt_sha256", a signature
failure and a broken chain link on the next line. Naming a different expected assayer fails.

### 5. One-command reproduction

```
bash tools/reproduce.sh python3   ->  tests OK; demo OK; independent check verified;
                                      receipts, events and transactions identical to evidence/demo-run
```

## Not run in this pass

* **No EVM.** Downloading Foundry and a Solidity compiler was refused by the build sandbox, so no
  contract was compiled or deployed, and the reference `AgenticCommerce.sol` was not executed.
  The escrow and gate are Python simulations of the pinned specification.
* No public testnet, no wallet, no real or test-network funds, no x402 facilitator, no ERC-8004
  registry.
* No external review: everything above was written and run by the same relay pass.

## Inherited claims (not re-run here)

* Lessons from an earlier offline prototype's review (office faults, freshness, receipt binding,
  concurrency and restart, sequential tokens) are restated in the decision record. That prototype
  is not in this repository and was not executed in this pass.
* Competitor and market facts in `docs/COMMERCIAL.md` come from the cited public sources and were
  not independently verified.
