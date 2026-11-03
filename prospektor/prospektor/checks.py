"""Deterministic acceptance checks.

Prototype check library for one machine-checkable job type, `roster/0`:
staff a set of event shifts from a pinned volunteer list. Producing a
good roster is a search problem; checking one is cheap and exact, which is
the kind of work an independent assay can verify without judgment.

Every check returns ("pass" | "fail" | "hold", detail). "fail" means an
agreed criterion is demonstrably violated by the provider's deliverable.
"hold" means the check could not decide. Nothing here reads free text
for instructions, calls a model, or uses the network or the clock.

Stages: "streak" checks need only the deliverable (cheap, every job).
"fire" checks need the pinned inputs (re-execution against evidence).
"human" checks cannot be machine-decided and always hold.
"""
from __future__ import annotations

import re

ID = re.compile(r"[A-Za-z0-9_-]{1,32}")  # always used with fullmatch: no trailing-newline quirk
MAX_ASSIGNMENTS = 5000
MAX_NOTES = 4000
SHOW = 5  # violations listed per finding; the count is always complete


def _list(items: list[str]) -> str:
    shown = "; ".join(items[:SHOW])
    return shown + (f"; and {len(items) - SHOW} more" if len(items) > SHOW else "")


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# Pinned input: the buyer's event (office-side data; problems here are HOLD)
# ---------------------------------------------------------------------------
def validate_event(event) -> list[str]:
    errs: list[str] = []
    if not isinstance(event, dict) or set(event) != {"format", "title", "shifts", "volunteers"}:
        return ["event must be an object with exactly format, title, shifts, volunteers"]
    if event["format"] != "prospektor.event/0":
        errs.append("event.format must be prospektor.event/0")
    seen = set()
    for i, sh in enumerate(event["shifts"] if isinstance(event["shifts"], list) else []):
        if not (isinstance(sh, dict) and set(sh) == {"id", "start", "end", "skill", "needed"}):
            errs.append(f"shift #{i} has the wrong fields")
            continue
        if not (isinstance(sh["id"], str) and ID.fullmatch(sh["id"])) or sh["id"] in seen:
            errs.append(f"shift #{i} id invalid or repeated")
            continue
        seen.add(sh["id"])
        if not (_is_int(sh["start"]) and _is_int(sh["end"]) and 0 <= sh["start"] < sh["end"]):
            errs.append(f"shift {sh['id']} times invalid")
        if not (_is_int(sh["needed"]) and sh["needed"] >= 1) or not isinstance(sh["skill"], str):
            errs.append(f"shift {sh['id']} needed/skill invalid")
    if not isinstance(event["shifts"], list) or not event["shifts"]:
        errs.append("event.shifts must be a non-empty list")
    seen = set()
    for i, vo in enumerate(event["volunteers"] if isinstance(event["volunteers"], list) else []):
        if not (isinstance(vo, dict) and set(vo) == {"id", "skills", "available"}):
            errs.append(f"volunteer #{i} has the wrong fields")
            continue
        if not (isinstance(vo["id"], str) and ID.fullmatch(vo["id"])) or vo["id"] in seen:
            errs.append(f"volunteer #{i} id invalid or repeated")
            continue
        seen.add(vo["id"])
        if not (isinstance(vo["skills"], list) and all(isinstance(s, str) for s in vo["skills"])):
            errs.append(f"volunteer {vo['id']} skills invalid")
        av = vo["available"]
        if not (isinstance(av, list) and all(isinstance(w, list) and len(w) == 2 and all(_is_int(t) for t in w)
                                             and 0 <= w[0] < w[1] for w in av)):
            errs.append(f"volunteer {vo['id']} availability invalid")
    if not isinstance(event["volunteers"], list) or not event["volunteers"]:
        errs.append("event.volunteers must be a non-empty list")
    return errs


def _index(event) -> tuple[dict, dict]:
    return ({s["id"]: s for s in event["shifts"]}, {v["id"]: v for v in event["volunteers"]})


def _resolved(doc, event):
    """Assignments whose shift and volunteer both exist (others are reported by refs_exist)."""
    shifts, vols = _index(event)
    return [(shifts[a["shift"]], vols[a["volunteer"]]) for a in doc["assignments"]
            if a["shift"] in shifts and a["volunteer"] in vols], shifts, vols


# ---------------------------------------------------------------------------
# Streak test: the deliverable alone
# ---------------------------------------------------------------------------
def format_roster_v0(params, doc, inputs):
    if not isinstance(doc, dict):
        return "fail", "deliverable is not a JSON object"
    required, optional = {"format", "assignments"}, {"notes"}
    keys = set(doc)
    if not required <= keys or keys - required - optional:
        return "fail", (f"top-level fields must be {sorted(required)} plus optional {sorted(optional)}; "
                        f"got {sorted(keys)}")
    if doc["format"] != "prospektor.roster/0":
        return "fail", "format must be prospektor.roster/0"
    asg = doc["assignments"]
    if not isinstance(asg, list) or not 1 <= len(asg) <= MAX_ASSIGNMENTS:
        return "fail", f"assignments must be a list of 1..{MAX_ASSIGNMENTS} items"
    bad = [f"#{i}" for i, a in enumerate(asg)
           if not (isinstance(a, dict) and set(a) == {"shift", "volunteer"}
                   and all(isinstance(a[k], str) and ID.fullmatch(a[k]) for k in ("shift", "volunteer")))]
    if bad:
        return "fail", f"{len(bad)} malformed assignment(s): {_list(bad)}"
    if "notes" in doc and not (isinstance(doc["notes"], str) and len(doc["notes"]) <= MAX_NOTES):
        return "fail", f"notes must be a string of at most {MAX_NOTES} characters"
    return "pass", f"{len(asg)} well-formed assignments"


def no_duplicate_assignments(params, doc, inputs):
    seen, dups = set(), []
    for a in doc["assignments"]:
        key = (a["shift"], a["volunteer"])
        if key in seen:
            dups.append(f"{a['volunteer']} on {a['shift']}")
        seen.add(key)
    return ("fail", f"{len(dups)} duplicate assignment(s): {_list(dups)}") if dups else ("pass", "no duplicates")


# ---------------------------------------------------------------------------
# Fire assay: re-execution against the pinned input
# ---------------------------------------------------------------------------
def refs_exist(params, doc, inputs):
    shifts, vols = _index(inputs["event"])
    bad = [f"{a['shift']}/{a['volunteer']}" for a in doc["assignments"]
           if a["shift"] not in shifts or a["volunteer"] not in vols]
    if bad:
        return "fail", f"{len(bad)} assignment(s) cite shifts or volunteers absent from the pinned input: {_list(bad)}"
    return "pass", f"all {len(doc['assignments'])} references resolve in the pinned input"


def coverage(params, doc, inputs):
    shifts, vols = _index(inputs["event"])
    staffed: dict[str, set] = {sid: set() for sid in shifts}
    for a in doc["assignments"]:
        if a["shift"] in shifts and a["volunteer"] in vols:
            staffed[a["shift"]].add(a["volunteer"])
    bad = [f"{sid} has {len(staffed[sid])}/{sh['needed']}" for sid, sh in sorted(shifts.items())
           if len(staffed[sid]) != sh["needed"]]
    if bad:
        return "fail", f"{len(bad)} shift(s) not staffed exactly as required: {_list(bad)}"
    return "pass", f"all {len(shifts)} shifts staffed exactly as required"


def qualified(params, doc, inputs):
    pairs, _, _ = _resolved(doc, inputs["event"])
    bad = sorted({f"{v['id']} lacks {s['skill']} for {s['id']}" for s, v in pairs if s["skill"] not in v["skills"]})
    return ("fail", f"{len(bad)} unqualified assignment(s): {_list(bad)}") if bad else ("pass", "every assignee has the shift's skill")


def available(params, doc, inputs):
    pairs, _, _ = _resolved(doc, inputs["event"])
    bad = sorted({f"{v['id']} unavailable for {s['id']} ({s['start']}-{s['end']})" for s, v in pairs
                  if not any(w[0] <= s["start"] and s["end"] <= w[1] for w in v["available"])})
    return ("fail", f"{len(bad)} assignment(s) outside stated availability: {_list(bad)}") if bad else (
        "pass", "every assignment falls inside the volunteer's availability")


def _by_volunteer(doc, event) -> dict[str, list]:
    pairs, _, _ = _resolved(doc, event)
    out: dict[str, list] = {}
    for s, v in pairs:
        if s not in out.setdefault(v["id"], []):
            out[v["id"]].append(s)
    for shifts in out.values():
        shifts.sort(key=lambda s: (s["start"], s["end"], s["id"]))
    return out


def no_overlap(params, doc, inputs):
    bad = []
    for vid, shifts in sorted(_by_volunteer(doc, inputs["event"]).items()):
        for i in range(len(shifts)):
            for j in range(i + 1, len(shifts)):
                a, b = shifts[i], shifts[j]
                if a["start"] < b["end"] and b["start"] < a["end"]:
                    bad.append(f"{vid} on {a['id']} and {b['id']} ({max(a['start'], b['start'])}-{min(a['end'], b['end'])})")
    return ("fail", f"{len(bad)} double booking(s): {_list(bad)}") if bad else ("pass", "no volunteer is double-booked")


def min_rest(params, doc, inputs):
    need = params.get("minutes")
    if not _is_int(need) or need < 0:
        return "hold", "criterion parameter 'minutes' is missing or invalid"
    bad = []
    for vid, shifts in sorted(_by_volunteer(doc, inputs["event"]).items()):
        for a, b in zip(shifts, shifts[1:]):
            gap = b["start"] - a["end"]
            if 0 <= gap < need:
                bad.append(f"{vid} rests {gap} min between {a['id']} and {b['id']}")
    return ("fail", f"{len(bad)} rest violation(s) under {need} min: {_list(bad)}") if bad else (
        "pass", f"every rest between shifts is at least {need} min")


def max_minutes(params, doc, inputs):
    cap = params.get("minutes")
    if not _is_int(cap) or cap <= 0:
        return "hold", "criterion parameter 'minutes' is missing or invalid"
    bad = []
    for vid, shifts in sorted(_by_volunteer(doc, inputs["event"]).items()):
        total = sum(s["end"] - s["start"] for s in shifts)
        if total > cap:
            bad.append(f"{vid} assigned {total} min")
    return ("fail", f"{len(bad)} volunteer(s) over {cap} min: {_list(bad)}") if bad else (
        "pass", f"no volunteer exceeds {cap} min")


# ---------------------------------------------------------------------------
# Human judgment: never machine-decided
# ---------------------------------------------------------------------------
def manual_review(params, doc, inputs):
    q = params.get("question", "unspecified")
    return "hold", f"needs human review, not machine-checkable: {q}"


CHECKS = {
    "format.roster_v0": ("streak", format_roster_v0, ()),
    "roster.no_duplicates": ("streak", no_duplicate_assignments, ()),
    "roster.refs_exist": ("fire", refs_exist, ("event",)),
    "roster.coverage": ("fire", coverage, ("event",)),
    "roster.qualified": ("fire", qualified, ("event",)),
    "roster.available": ("fire", available, ("event",)),
    "roster.no_overlap": ("fire", no_overlap, ("event",)),
    "roster.min_rest": ("fire", min_rest, ("event",)),
    "roster.max_minutes": ("fire", max_minutes, ("event",)),
    "manual.review": ("human", manual_review, ()),
}

INPUT_VALIDATORS = {"event": validate_event}
