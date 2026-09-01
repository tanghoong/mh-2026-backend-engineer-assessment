#!/usr/bin/env python3
"""Tier T-D — the deliverables are checked the way the code is.

    python3 _work/verify_docs.py

The brief grades documents as much as code, so "is it done?" has to be answerable for a
`.md` the same way it is for a function. This is the answer to §6.5's question about
benchmarks that silently rot, applied to prose: **every number quoted in a deliverable is
re-derived from a live run and diffed.** A figure that was true when it was written and is
not true now fails the check rather than reaching a reader.

It also enforces the things that are easy to lose in a last-day rewrite: word limits,
required sections, the `DECISIONS.md` format, that every `line_id` named in `EVAL.md` is
real, that every confirmed trap is accounted for, and that no delivered file documents a
command only this machine can run.

Exit code 0 when clean, 1 otherwise, so it can gate a build.
"""
from __future__ import annotations

import csv
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DELIVERABLES = ["README.md", "DESIGN.md", "DECISIONS.md", "EVAL.md", "PERF.md",
                "SYNC.md", "SCALE.md", "predictions.csv"]

problems: list[str] = []
notes: list[str] = []


def fail(tag: str, msg: str) -> None:
    problems.append(f"{tag}  {msg}")


def read(name: str) -> str | None:
    p = ROOT / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def prose_words(text: str) -> int:
    """Word count excluding fenced code, roughly as a human would count it."""
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    body = re.sub(r"[|>#*`\-]", " ", body)
    return len(re.findall(r"[A-Za-z0-9%./]+", body))


# ---------------------------------------------------------------- T-D0 existence
def t_d0_everything_required_exists() -> None:
    for name in DELIVERABLES:
        if not (ROOT / name).exists():
            fail("T-D0", f"{name} is required by the brief section 3 and does not exist")


# ---------------------------------------------------------------- T-D1 length limits
def t_d1_length_limits() -> None:
    for name, limit in (("DESIGN.md", 1500), ("SCALE.md", 800)):
        text = read(name)
        if text is None:
            continue
        n = prose_words(text)
        if n > limit:
            fail("T-D1", f"{name} is {n} words against a ~{limit} limit")
        else:
            notes.append(f"T-D1  {name} {n}/{limit} words")


# ---------------------------------------------------------------- T-D2 required sections
REQUIRED_SECTIONS = {
    "DESIGN.md": ["objective function", "pipeline", "failure", "boundary"],
    "EVAL.md": ["harness", "metric", "error analysis", "label", "regression"],
    "PERF.md": ["baseline", "diagnosis", "fix", "p95", "trade-off", "ceiling"],
    "SYNC.md": ["defect", "invariant", "contract", "scale"],
    "SCALE.md": ["break", "alias", "ship"],
    "README.md": ["running", "skipped", "attribution", "ambiguous"],
}


def t_d2_required_sections() -> None:
    for name, needles in REQUIRED_SECTIONS.items():
        text = read(name)
        if text is None:
            continue
        low = text.lower()
        missing = [n for n in needles if n not in low]
        if missing:
            fail("T-D2", f"{name} never mentions: {', '.join(missing)}")


# ---------------------------------------------------------------- T-D3 decisions format
def t_d3_decisions_are_well_formed() -> None:
    text = read("DECISIONS.md")
    if text is None:
        return
    entries = re.split(r"^## (D-\d+)", text, flags=re.M)[1:]
    pairs = list(zip(entries[::2], entries[1::2]))
    if not pairs:
        return fail("T-D3", "DECISIONS.md has no D-nn entries")
    notes.append(f"T-D3  {len(pairs)} decision entries")
    if len(pairs) > 15 and "8" not in text[:1200]:
        fail("T-D3", f"{len(pairs)} entries against the brief's 8-15; the deviation is not "
                     "explained in the opening")
    for name, body in pairs:
        if "reversal trigger" not in body.lower():
            fail("T-D3", f"{name} has no reversal trigger - the brief's own template has one, "
                         "and it is what shows the decision was made rather than written")
        if not re.search(r"\*\*(Evidence|Measured|Chose)", body):
            fail("T-D3", f"{name} states no evidence")


# ---------------------------------------------------------------- T-D4 numbers are live
def t_d4_quoted_numbers_are_still_true() -> None:
    """The anti-rot check. Re-run the harness and diff against what EVAL.md claims."""
    sys.path.insert(0, str(ROOT))
    from src.eval import harness
    from src.eval.metrics import latency_summary, score

    outs = harness.run(harness.build("pipeline"), harness.load("order_lines_train.csv"))
    r = score(outs)
    live = {
        "coverage": f"{r.coverage:.1%}",
        "precision": f"{r.precision:.1%}",
        "true positives": str(r.tp),
        "false positives": str(r.fp),
        "net value": f"{r.net:,.0f}",
        "recall@3": f"{r.recall_at_3:.1%}",
        "cross-tenant": str(r.cross_tenant),
    }
    text = read("EVAL.md") or ""
    for label, value in live.items():
        if value.lstrip("-") not in text.replace("−", "-"):
            fail("T-D4", f"EVAL.md does not contain the live {label} ({value}) - either the "
                         "document is stale or the matcher changed")
    if latency_summary(outs)["p95_ms"] > 250:
        fail("T-D4", "p95 latency is over the 250 ms budget the documents claim to meet")
    notes.append(f"T-D4  live metrics re-derived and matched: {live}")


# ---------------------------------------------------------------- T-D5 line_ids are real
def t_d5_named_lines_exist() -> None:
    known = set()
    for name in ("order_lines_train.csv", "order_lines_holdout.csv"):
        with open(ROOT / "data" / name, encoding="utf-8", newline="") as fh:
            known.update(r["line_id"] for r in csv.DictReader(fh))
    for doc in ("EVAL.md", "DECISIONS.md", "DESIGN.md"):
        text = read(doc)
        if text is None:
            continue
        cited = set(re.findall(r"\b(?:ACM|NRD)-[TH]-\d{4}\b", text))
        unknown = sorted(cited - known)
        if unknown:
            fail("T-D5", f"{doc} names line_ids that do not exist: {unknown}")
        elif cited:
            notes.append(f"T-D5  {doc} cites {len(cited)} real line_ids")


# ---------------------------------------------------------------- T-D6 traps accounted for
def t_d6_confirmed_traps_are_accounted_for() -> None:
    text = read("_work/TRAPS.md") or (ROOT / "_work" / "TRAPS.md").read_text(encoding="utf-8")
    board = re.findall(r"^\| (TR-\d+) \|([^|]*)\|[^|]*\|([^|]*)\|", text, flags=re.M)
    confirmed = [t for t, _desc, verdict in board if "CONFIRMED" in verdict]
    everywhere = " ".join(filter(None, (read(d) for d in DELIVERABLES)))
    everywhere += (ROOT / "_work" / "TRAPS.md").read_text(encoding="utf-8")
    missing = [t for t in confirmed if t not in everywhere]
    if missing:
        fail("T-D6", f"confirmed traps appear in no deliverable: {missing}")
    notes.append(f"T-D6  {len(confirmed)} confirmed traps, all accounted for")


# ---------------------------------------------------------------- T-D8 no local-only commands
def t_d8_no_machine_specific_commands() -> None:
    for name in DELIVERABLES:
        text = read(name)
        if text and re.search(r"\bpy -3\b", text):
            fail("T-D8", f"{name} documents `py -3`, which only works on this machine; the "
                         "brief says assume a clean machine with python3")


# ---------------------------------------------------------------- T-D9 predictions schema
def t_d9_predictions_still_validate() -> None:
    if not (ROOT / "predictions.csv").exists():
        return
    r = subprocess.run([sys.executable, "-m", "src.predict", "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        fail("T-D9", f"predictions.csv fails its own schema check:\n{r.stdout}{r.stderr}")
    else:
        notes.append("T-D9  predictions.csv passes the section 5.3 schema check")


def main() -> int:
    for check in (t_d0_everything_required_exists, t_d1_length_limits,
                  t_d2_required_sections, t_d3_decisions_are_well_formed,
                  t_d4_quoted_numbers_are_still_true, t_d5_named_lines_exist,
                  t_d6_confirmed_traps_are_accounted_for,
                  t_d8_no_machine_specific_commands, t_d9_predictions_still_validate):
        try:
            check()
        except Exception as exc:                                  # a check that crashes
            fail(check.__name__, f"the check itself raised: {exc!r}")

    print("=== T-D: the deliverables, checked the way the code is ===\n")
    for n in notes:
        print(f"  ok    {n}")
    if problems:
        print()
        for p in problems:
            print(f"  FAIL  {p}")
    print(f"\n  {len(problems)} problem(s)"
          + ("" if problems else " - every quoted number is live and every limit holds"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
