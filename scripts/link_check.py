#!/usr/bin/env python3
"""
link_check.py — Find dangling pointers and orphaned notes in a memory vault.

A pointer that resolves to nothing is worse than no pointer: the agent learns
that the memory file lies, then stops trusting every rule in it. This catches
that before it happens.

Checks:
  1. [[wikilinks]] whose target note does not exist
  2. markdown links to local .md files that do not exist
  3. notes with zero inbound and zero outbound links (orphans)
  4. duplicate note names, which make wikilinks ambiguous

Usage:
    python3 scripts/link_check.py --vault ./vault
    python3 scripts/link_check.py --vault ./vault --json

Exit code 1 when any dangling link is found, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WIKILINK = re.compile(r"\[\[([^\[\]]+?)\]\]")
MDLINK = re.compile(r"\[[^\]]*\]\(([^)]+\.md)(?:#[^)]*)?\)")
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")

# Template notes intentionally contain placeholder links. AGENTS.md is a
# contract, not a note, so it participates in no link graph.
SKIP_DIRS = {"90-templates", ".obsidian", ".git"}
SKIP_FILES = {"AGENTS.md"}


def strip_code(text: str) -> str:
    """Remove fenced and inline code: a syntax example is not a real link."""
    return INLINE_CODE.sub("", FENCE.sub("", text))


def is_scannable(rel: Path, include_templates: bool) -> bool:
    if rel.name in SKIP_FILES:
        return False
    parts = set(rel.parts[:-1])
    if not include_templates and parts & SKIP_DIRS:
        return False
    return True


def note_key(rel: Path) -> str:
    """Wikilinks usually omit the directory and the extension."""
    return rel.stem


def scan(vault: Path, include_templates: bool = False) -> dict:
    notes = sorted(
        p for p in vault.rglob("*.md")
        if p.is_file() and is_scannable(p.relative_to(vault), include_templates)
    )
    by_key: dict = {}
    rels = {}
    for p in notes:
        rel = p.relative_to(vault)
        rels[p] = rel
        by_key.setdefault(note_key(rel).lower(), []).append(rel)

    dangling = []
    local_links_bad = []
    outbound: dict = {p: set() for p in notes}
    inbound: dict = {p: set() for p in notes}
    duplicate_names = {k: [str(r) for r in v] for k, v in by_key.items() if len(v) > 1}

    for p in notes:
        raw = p.read_text(encoding="utf-8", errors="ignore")
        body = strip_code(raw)
        rel = rels[p]

        for target in WIKILINK.findall(body):
            name = target.split("|")[0].split("#")[0].strip()
            if not name:
                continue
            key = name.lower()
            hits = by_key.get(key)
            if not hits:
                # tolerate a path-qualified wikilink like [[01-projects/foo]]
                tail = name.split("/")[-1].lower()
                hits = by_key.get(tail)
            if hits:
                for h in hits:
                    target_path = vault / h
                    outbound[p].add(target_path)
                    if target_path in inbound:
                        inbound[target_path].add(p)
            else:
                dangling.append({"from": str(rel), "target": name})

        for link in MDLINK.findall(body):
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            candidate = (p.parent / link).resolve()
            if not candidate.is_file():
                local_links_bad.append({"from": str(rel), "target": link})

    orphans = [
        str(rels[p]) for p in notes
        if not outbound[p] and not inbound[p]
    ]

    return {
        "vault": str(vault),
        "note_count": len(notes),
        "link_count": sum(len(v) for v in outbound.values()),
        "dangling": dangling,
        "broken_local_links": local_links_bad,
        "orphans": orphans,
        "duplicate_names": duplicate_names,
        "ok": not dangling and not local_links_bad,
    }


def render(report: dict) -> str:
    out = []
    add = out.append
    add("=" * 64)
    add("LINK CHECK")
    add("=" * 64)
    add(f"vault   {report['vault']}")
    add(f"notes   {report['note_count']}")
    add(f"links   {report['link_count']}")
    add("")

    if report["dangling"]:
        add(f"DANGLING WIKILINKS ({len(report['dangling'])})")
        for d in report["dangling"][:40]:
            add(f"  {d['from']}  ->  [[{d['target']}]]")
        if len(report["dangling"]) > 40:
            add(f"  ... and {len(report['dangling']) - 40} more")
        add("")
    else:
        add("dangling wikilinks: none")
        add("")

    if report["broken_local_links"]:
        add(f"BROKEN FILE LINKS ({len(report['broken_local_links'])})")
        for d in report["broken_local_links"][:20]:
            add(f"  {d['from']}  ->  {d['target']}")
        add("")

    if report["duplicate_names"]:
        add(f"AMBIGUOUS NOTE NAMES ({len(report['duplicate_names'])})")
        for k, v in list(report["duplicate_names"].items())[:10]:
            add(f"  {k}: {', '.join(v)}")
        add("")

    if report["orphans"]:
        add(f"ORPHANS — no inbound, no outbound ({len(report['orphans'])})")
        for o in report["orphans"][:20]:
            add(f"  {o}")
        if len(report["orphans"]) > 20:
            add(f"  ... and {len(report['orphans']) - 20} more")
        add("")

    add("VERDICT  " + ("PASS — every pointer resolves" if report["ok"] else "FAIL — fix dangling links before shipping"))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check pointer integrity in a memory vault.")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--include-templates", action="store_true",
                    help="also scan 90-templates (placeholder links will fail)")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 2

    report = scan(vault, args.include_templates)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
