# SPDX-License-Identifier: MPL-2.0
"""Compare two arm_parity_dump.py / benchmark_money.py result sets (x86 vs ARM).

    python scripts/arm_parity_compare.py <x86_dir> <arm_dir>

Each directory holds dump_<level>.json files and money benchmark
scores/<label>.jsonl + .picks.jsonl caches. Prints a markdown report (also
appended to $GITHUB_STEP_SUMMARY when set) and exits non-zero if any decision
differs.
"""
from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _jsonl(p: Path) -> dict:
    return {r["key"]: r for r in map(json.loads, p.read_text().splitlines()) if r}


def _junit(p: Path) -> dict[str, str]:
    """test id -> outcome (passed / failed / error / skipped)."""
    out = {}
    for tc in ET.parse(p).getroot().iter("testcase"):
        tid = f"{tc.get('classname')}::{tc.get('name')}"
        kinds = [c.tag for c in tc if c.tag in ("failure", "error", "skipped")]
        out[tid] = {"failure": "failed"}.get(kinds[0], kinds[0]) if kinds else "passed"
    return out


def compare_dump(a: dict, b: dict) -> tuple[list[str], bool]:
    n_cp = len(a["checker"])
    pick_diff = order_diff = 0
    max_eq = 0.0
    for ma, mb in zip(a["checker"], b["checker"]):
        if ma[0][0] != mb[0][0]:
            pick_diff += 1
        if [m[0] for m in ma] != [m[0] for m in mb]:
            order_diff += 1
        da = {tuple(m[0]): m[1] for m in ma}
        for brd, eq in mb:
            if tuple(brd) in da:
                max_eq = max(max_eq, abs(da[tuple(brd)] - eq))
    act_diff = 0
    max_cube = 0.0
    for ca, cb in zip(a["cube"], b["cube"]):
        act_diff += ca[3] != cb[3]
        max_cube = max(max_cube, *(abs(x - y) for x, y in zip(ca[:3], cb[:3])))
    lines = [
        f"| {a['level']} | {n_cp} | {pick_diff} | {order_diff} | {max_eq:.2e} "
        f"| {len(a['cube'])} | {act_diff} | {max_cube:.2e} "
        f"| {a['seconds']['checker'] + a['seconds']['cube']:.0f}s / "
        f"{b['seconds']['checker'] + b['seconds']['cube']:.0f}s |"
    ]
    return lines, pick_diff == 0 and act_diff == 0


def main() -> int:
    x86, arm = Path(sys.argv[1]), Path(sys.argv[2])
    ok = True
    out = ["## x86_64 vs aarch64 (NEON) parity", "",
           "### Raw outputs, money benchmark positions", "",
           "| level | checker | best move differs | top-5 order differs | max equity diff "
           "| cube | action differs | max ND/DT/DP diff | time x86 / arm |",
           "|---|---|---|---|---|---|---|---|---|"]
    for fa in sorted(x86.glob("dump_*.json")):
        fb = arm / fa.name
        if not fb.exists():
            out.append(f"| {fa.stem} | missing on ARM |"); ok = False; continue
        lines, same = compare_dump(json.loads(fa.read_text()), json.loads(fb.read_text()))
        out += lines; ok &= same

    out += ["", "### Money benchmark PR (16,889 decisions vs rollout reference)", "",
            "| label | x86 PR | arm PR | picks differing |", "|---|---|---|---|"]
    for fa in sorted(x86.glob("scores/*.picks.jsonl")):
        fb = arm / "scores" / fa.name
        label = fa.name.removesuffix(".picks.jsonl")
        pa, pb = _jsonl(fa), _jsonl(fb) if fb.exists() else {}
        diff = sum(1 for k in pa if k not in pb or pa[k]["pick"] != pb[k]["pick"])
        prs = []
        for d in (x86, arm):
            f = d / "scores" / f"{label}.pr.json"
            prs.append(json.loads(f.read_text()) if f.exists() else None)
        fmt = lambda r: (f"{r['total_pr']:.3f} (chk {r['checker_pr']:.3f}, cube {r['cube_pr']:.3f})"
                         if r else "n/a")
        out.append(f"| {label} | {fmt(prs[0])} | {fmt(prs[1])} | {diff} / {len(pa)} |")
        ok &= diff == 0

    ja, jb = x86 / "pytest.xml", arm / "pytest.xml"
    if ja.exists() and jb.exists():
        ta, tb = _junit(ja), _junit(jb)
        count = lambda t, k: sum(v == k for v in t.values())
        out += ["", "### pytest tests/", "",
                "| | passed | failed | error | skipped |", "|---|---|---|---|---|"]
        for name, t in (("x86_64", ta), ("aarch64", tb)):
            out.append(f"| {name} | " + " | ".join(str(count(t, k)) for k in
                       ("passed", "failed", "error", "skipped")) + " |")
        differ = sorted(k for k in ta.keys() | tb.keys() if ta.get(k) != tb.get(k))
        out.append("")
        out.append(f"Tests with a different outcome on ARM: **{len(differ)}**")
        out += [f"- `{k}`: x86 {ta.get(k)}, arm {tb.get(k)}" for k in differ]
        failing = sorted(k for k, v in ta.items() if v in ("failed", "error") and tb.get(k) == v)
        if failing:
            out.append("")
            out.append("Failing identically on both (not ARM-related):")
            out += [f"- `{k}`" for k in failing]
        ok &= not differ
    else:
        out += ["", "pytest results missing"]; ok = False

    out += ["", f"**Result: {'IDENTICAL decisions' if ok else 'DIFFERENCES FOUND'}**"]
    report = "\n".join(out)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
