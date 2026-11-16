#!/usr/bin/env python3
"""
budget_check.py — Does the discipline layer fit in the host's injection budget?

The failure mode people miss: hosts that inject a memory file usually have a
ceiling, and when you cross it they inject **nothing**, not a truncated version.
A file at 4200 characters under a 4000 cap silently disables all your rules.

This measures the file, finds which section eats the budget, and tells you what
to cut.

Usage:
    python3 scripts/budget_check.py --config ./memory.config.json
    python3 scripts/budget_check.py --file ./CLAUDE.md --budget 4000
    python3 scripts/budget_check.py --file ./CLAUDE.md --budget 4000 --json

Exit code 1 when over budget.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Why 3800 and not 4000: leave headroom for the host to append its own wrapper
# text around the injected block.
DEFAULT_SAFETY = 0.95


def split_sections(text: str) -> list:
    """Return [(heading, char_count)] so the report can say where the fat is."""
    lines = text.splitlines(keepends=True)
    sections = []
    current = "(preamble)"
    buf = []
    for line in lines:
        if re.match(r"^#{1,3}\s+", line):
            if buf:
                sections.append((current, sum(len(x) for x in buf)))
            current = line.strip().lstrip("#").strip()
            buf = [line]
        else:
            buf.append(line)
    if buf:
        sections.append((current, sum(len(x) for x in buf)))
    return sections


def analyze(path: Path, budget: int, safety: float) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    chars = len(text)
    chars_nospace = len(re.sub(r"\s", "", text))
    effective_cap = int(budget * safety)
    sections = split_sections(text)
    sections.sort(key=lambda s: s[1], reverse=True)

    over = chars > effective_cap
    # How much to cut, in characters, to fit the safe cap.
    cut_needed = max(0, chars - effective_cap)

    return {
        "file": str(path),
        "budget": budget,
        "safety_factor": safety,
        "effective_cap": effective_cap,
        "chars": chars,
        "chars_no_whitespace": chars_nospace,
        "line_count": text.count("\n") + 1,
        "usage_pct": round(chars / budget * 100, 1) if budget else 0,
        "headroom": effective_cap - chars,
        "over_budget": over,
        "cut_needed": cut_needed,
        "largest_sections": [{"section": s, "chars": c} for s, c in sections[:6]],
        "ok": not over,
    }


def render(r: dict) -> str:
    out = []
    add = out.append
    add("=" * 64)
    add("BUDGET CHECK")
    add("=" * 64)
    add(f"file      {r['file']}")
    add(f"budget    {r['budget']} chars  (safe cap {r['effective_cap']} = {int(r['safety_factor']*100)}%)")
    add(f"actual    {r['chars']} chars  ({r['usage_pct']}% of budget)")
    add(f"headroom  {r['headroom']:+d} chars")
    add("")

    add("largest sections")
    for s in r["largest_sections"]:
        pct = s["chars"] / r["chars"] * 100 if r["chars"] else 0
        bar = "." * max(1, int(pct / 4))
        add(f"  {s['chars']:>5}c {pct:>5.1f}%  {bar:<25} {s['section'][:44]}")
    add("")

    if r["over_budget"]:
        add(f"VERDICT  FAIL — {r['cut_needed']} chars over the safe cap.")
        add("")
        add("  The host will inject NOTHING at this size, not a truncated copy.")
        add("  Cut in this order:")
        add("    1. merge duplicate rules that say the same thing twice")
        add("    2. drop anything the tool already enforces by itself")
        add("    3. move examples into a vault note, leave one pointer line")
        add("    4. shorten the biggest section above, not the smallest")
    else:
        add(f"VERDICT  PASS — {r['headroom']} chars of headroom.")
        if r["usage_pct"] > 85:
            add("         Above 85%: the next rule you add will break it. Trim now.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check the discipline layer against the host budget.")
    ap.add_argument("--config", help="memory.config.json written by scaffold.py")
    ap.add_argument("--file", help="discipline file to measure")
    ap.add_argument("--budget", type=int, help="character budget")
    ap.add_argument("--safety", type=float, default=DEFAULT_SAFETY,
                    help=f"fraction of budget treated as safe cap (default {DEFAULT_SAFETY})")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    file_path = args.file
    budget = args.budget

    if args.config:
        cfg_path = Path(args.config).expanduser().resolve()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        file_path = file_path or cfg.get("discipline_file")
        budget = budget or cfg.get("discipline_budget_chars")
        # A relative path in the config is relative to the config file, not the cwd.
        if file_path and not Path(file_path).is_absolute():
            file_path = str(cfg_path.parent / file_path)

    if not file_path or not budget:
        print("error: need --file and --budget, or a --config containing both", file=sys.stderr)
        return 2

    p = Path(file_path).expanduser().resolve()
    if not p.is_file():
        print(f"error: file not found: {p}", file=sys.stderr)
        return 2

    report = analyze(p, int(budget), args.safety)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
