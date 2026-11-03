"""Command line: `python3 -m prospektor <command>` from the prospektor/ folder.

  demo   [--out DIR] [--quiet]        five jobs and nine attacks on the simulated escrow
  check  --terms F --input NAME=F --deliverable F [--json]
                                      run the engine offline (a self-check; never an attestation)
  verify RECEIPTS.jsonl               re-derive every hash, signature and chain link in a receipt log
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .canonical import StrictJSONError, strict_loads
from .engine import ENGINE_VERSION, evaluate, validate_terms
from .ledger import Ledger


def _check(args) -> int:
    try:
        terms = strict_loads(Path(args.terms).read_bytes())
    except (OSError, StrictJSONError) as exc:
        print(f"cannot read terms: {exc}", file=sys.stderr)
        return 2
    errs = validate_terms(terms)
    if errs:
        print("terms are invalid: " + "; ".join(errs), file=sys.stderr)
        return 2
    inputs = {}
    for item in args.input or []:
        name, _, path = item.partition("=")
        inputs[name] = Path(path).read_bytes()
    ev = evaluate(terms, inputs, Path(args.deliverable).read_bytes(), None)
    crit = [f for f in ev.findings if f.stage != "intake" or f.result == "hold"]
    results = {f.result for f in crit}
    selfcheck = "FAIL" if "fail" in results else "HOLD" if "hold" in results else "CRITERIA PASS"
    out = ev.as_dict() | {"engine_version": ENGINE_VERSION, "self_check": selfcheck,
                          "note": "Offline self-check: no escrow state was read and nothing was signed. "
                                  "It can never authorize payment; only a signed assay of the escrowed job can."}
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(f"self-check: {selfcheck}")
        for f in ev.findings:
            print(f"  {f.result:11} {f.stage:6} {f.criterion:9} {f.check:24} {f.detail}")
        print(out["note"])
    return {"CRITERIA PASS": 0, "HOLD": 3, "FAIL": 4}[selfcheck]


def _verify(args) -> int:
    problems = Ledger(args.receipts).verify()
    if problems:
        for p in problems:
            print(p)
        return 1
    print(f"ok: {len(Ledger(args.receipts).entries())} receipts; every hash, signature and chain link re-derived")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m prospektor", description="PROSPEKTOR prototype (simulation only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the end-to-end demonstration")
    d.add_argument("--out", help="evidence folder (default: a new temporary folder)")
    d.add_argument("--quiet", action="store_true")
    c = sub.add_parser("check", help="offline self-check of a deliverable against terms")
    c.add_argument("--terms", required=True)
    c.add_argument("--input", action="append", help="NAME=PATH for each pinned input")
    c.add_argument("--deliverable", required=True)
    c.add_argument("--json", action="store_true")
    v = sub.add_parser("verify", help="verify a receipt log")
    v.add_argument("receipts")
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        from .demo import run
        return 0 if run(args.out, args.quiet)["ok"] else 1
    if args.cmd == "check":
        return _check(args)
    return _verify(args)


if __name__ == "__main__":
    sys.exit(main())
