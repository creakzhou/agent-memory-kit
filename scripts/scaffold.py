#!/usr/bin/env python3
"""
scaffold.py — Generate a three-layer memory system adapted to the detected host.

Zero dependencies. Python 3.8+.

Layer model:
    L1 identity   follows the account, injected every turn      -> platform cloud memory
    L2 discipline hard rules, hard budget, injected per session -> CLAUDE.md / AGENTS.md / MEMORY.md
    L3 facts      notes retrieved on demand                     -> markdown vault + index + wikilinks

What this script writes:
    <vault>/                     the fact layer (plain markdown, no lock-in)
      AGENTS.md                  contract for any agent entering the vault
      00-index.md                the single entry point
      01-projects/ ... 90-templates/
    <rules-dir>/<rule file>      the discipline layer, filename chosen per platform
    <rules-dir>/memory.config.json

It never overwrites an existing file unless you pass --force.

Usage:
    python3 scripts/scaffold.py --target ~/memory-vault --name "Alex"
    python3 scripts/scaffold.py --target ~/memory-vault --dry-run
    python3 scripts/scaffold.py --target ./vault --rules-dir . --platform codex
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"

# Numbered prefixes: the number IS the category. No folder intuition required.
LAYOUT = [
    ("01-projects",   "Active work. One note per project."),
    ("03-preferences", "How I want things done. Durable, not situational."),
    ("04-decisions",  "Decisions with a reason attached. Append-only."),
    ("05-reviews",    "Daily / weekly retrospectives."),
    ("10-archive",    "Finished or dead. Kept for retrieval, not for reading."),
    ("20-notes",      "Reference material that has no project home."),
    ("30-outputs",    "Deliverables that left the building."),
    ("90-templates",  "Note shapes. Copy, do not edit in place."),
]

# Per-platform discipline-layer filename and injection ceiling (characters).
PLATFORM_RULES = {
    "claude-code": {"file": "CLAUDE.md",     "budget": 4000, "auto": "hook"},
    "codex":       {"file": "AGENTS.md",     "budget": 4000, "auto": "manual"},
    "workbuddy":   {"file": "MEMORY.md",     "budget": 3800, "auto": "manual"},
    "dsh":         {"file": "AGENTS.md",     "budget": 4000, "auto": "hook"},
    "cursor":      {"file": ".cursor/rules/memory.mdc", "budget": 3000, "auto": "manual"},
    "gemini-cli":  {"file": "GEMINI.md",     "budget": 4000, "auto": "manual"},
    "generic":     {"file": "AGENTS.md",     "budget": 3800, "auto": "manual"},
}


def load_probe(path):
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        print(f"warn: probe file not found at {p}, falling back to defaults", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def choose_platform(probe, explicit):
    if explicit:
        return explicit
    if probe and probe.get("primary_agent"):
        return probe["primary_agent"]
    return "generic"


def build_recall_section(caps: dict) -> str:
    """The recall block differs by what the host can actually do. Never lie here."""
    if caps.get("auto_recall_hook"):
        return (
            "## Recall (hook mode)\n\n"
            "A lifecycle hook recalls before each turn. Trust it. Do not recall the\n"
            "same topic twice in one turn — duplicating the hook only burns context."
        )
    if caps.get("hook_capable"):
        return (
            "## Recall triggers (hook available, not configured)\n\n"
            "This host supports lifecycle hooks but none is enabled yet. Until one is,\n"
            "recall is manual. Trigger it yourself when:\n\n"
            "- the request references a previous session or an earlier decision\n"
            "- the task starts in a domain that likely has prior decisions\n"
            "- the instruction conflicts with a rule you think you remember\n"
            "- you are about to say \"as we discussed earlier\"\n\n"
            "If you skip recall, say so in one line instead of guessing."
        )
    return (
        "## Recall triggers (manual mode)\n\n"
        "This host has no lifecycle hook. Nothing is injected automatically. Recall\n"
        "happens only when you decide to, so decide at these moments, every time,\n"
        "without being asked:\n\n"
        "- the request references a previous session or an earlier decision\n"
        "- the task starts in a domain that likely has prior decisions\n"
        "- the instruction conflicts with a rule you think you remember\n"
        "- you are about to say \"as we discussed earlier\"\n\n"
        "If you skip recall, say so in one line. Do not reconstruct history from vibes."
    )


def render(text: str, vars: dict) -> str:
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def build_files(vault: Path, rules_dir: Path, platform: str, name: str, probe) -> list:
    """Return [(path, content, kind)] that the plan will write."""
    cfg = PLATFORM_RULES.get(platform, PLATFORM_RULES["generic"])
    caps = (probe or {}).get("capability_summary", {})
    hooks_on = bool(caps.get("auto_recall_hook"))
    mcp_on = bool(caps.get("mcp_available"))

    auto_mode = "hook" if hooks_on else ("hook-capable (not configured)" if caps.get("hook_capable") else "manual")
    vars = {
        "NAME": name,
        "DATE": date.today().isoformat(),
        "VAULT": str(vault),
        "PLATFORM": platform,
        "BUDGET": cfg["budget"],
        "AUTO_MODE": auto_mode,
        "INDEX": str(vault / "00-index.md"),
        "MCP_STATUS": "configured" if mcp_on else "not configured",
    }
    vars["RECALL_SECTION"] = build_recall_section(caps)

    files = []

    def add(path: Path, tpl_name: str, kind: str, extra: dict = None):
        tpl = (TPL / tpl_name).read_text(encoding="utf-8")
        local = dict(vars)
        local.update(extra or {})
        files.append((path, render(tpl, local), kind))

    add(vault / "AGENTS.md", "vault-AGENTS.md.tpl", "fact-layer contract")
    add(vault / "00-index.md", "vault-00-index.md.tpl", "fact-layer index")
    add(vault / "90-templates" / "note.md", "note.md.tpl", "template")

    # Two starter notes so the very first audit passes: the index links them,
    # and they link each other, so neither is an orphan.
    add(vault / "03-preferences" / "about-me.md", "starter.md.tpl", "starter note", {
        "TITLE": "How I work",
        "LINKS": "[[working-agreements]]",
        "PURPOSE": "So a new session does not start by interviewing me again. "
                   "Fill in: language and tone, output shape (conclusions first? tables?), "
                   "what I will not tolerate, and when I want options instead of an answer.",
    })
    add(vault / "03-preferences" / "working-agreements.md", "starter.md.tpl", "starter note", {
        "TITLE": "Working agreements",
        "LINKS": "[[about-me]]",
        "PURPOSE": "Rules that outlive any single project. If a rule only applies to one "
                   "project, it belongs in that project's note instead.",
    })

    rule_path = rules_dir / cfg["file"]
    add(rule_path, "discipline.md.tpl", "discipline layer")

    cfg_payload = {
        "version": 1,
        "platform": platform,
        "vault": str(vault),
        "discipline_file": str(rule_path),
        "discipline_budget_chars": cfg["budget"],
        "recall": {
            "mode": "hook" if hooks_on else "manual",
            "hook_capable": bool(caps.get("hook_capable")),
            "note": "manual means the agent only recalls when told to, or when the discipline file forces it",
        },
        "backend": {
            "kind": "filesystem" if not mcp_on else "mcp-or-filesystem",
            "mcp_configured": mcp_on,
            "options": ["filesystem", "mcp-filesystem", "memos", "git"],
        },
    }
    files.append((rules_dir / "memory.config.json",
                  json.dumps(cfg_payload, indent=2) + "\n", "config"))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a three-layer agent memory system.")
    ap.add_argument("--target", required=True, help="vault path (fact layer)")
    ap.add_argument("--rules-dir", default=".", help="where the discipline layer goes (default: cwd)")
    ap.add_argument("--platform", help="force a platform id instead of reading the probe")
    ap.add_argument("--probe", help="env.probe.json produced by probe.py")
    ap.add_argument("--name", default="(your name)", help="how the agent should address you")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    ap.add_argument("--force", action="store_true", help="overwrite files that already exist")
    args = ap.parse_args()

    vault = Path(os.path.expanduser(args.target)).resolve()
    rules_dir = Path(os.path.expanduser(args.rules_dir)).resolve()
    probe = load_probe(args.probe)
    platform = choose_platform(probe, args.platform)

    if platform not in PLATFORM_RULES:
        print(f"error: unknown platform '{platform}'. known: {', '.join(PLATFORM_RULES)}",
              file=sys.stderr)
        return 2

    files = build_files(vault, rules_dir, platform, args.name, probe)

    print("=" * 68)
    print("SCAFFOLD PLAN")
    print("=" * 68)
    print(f"platform   {platform}  (discipline file: {PLATFORM_RULES[platform]['file']})")
    print(f"vault      {vault}")
    print(f"rules dir  {rules_dir}")
    print("")

    planned = 0
    skipped = 0
    for path, content, kind in files:
        exists = path.exists()
        flag = "SKIP exists" if exists and not args.force else "write"
        if exists and not args.force:
            skipped += 1
        else:
            planned += 1
        print(f"  [{flag:>11}] {path}")
        print(f"                {kind}, {len(content)} chars")

    print("")
    dirs = [vault / d for d, _ in LAYOUT]
    for d in dirs:
        state = "exists" if d.exists() else "create"
        print(f"  [dir {state:>7}] {d}")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    vault.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)

    for path, content, kind in files:
        if path.exists() and not args.force:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"\nwrote {planned} files, skipped {skipped}")
    print("\nnext:")
    print(f"  python3 scripts/budget_check.py --config {rules_dir / 'memory.config.json'}")
    print(f"  python3 scripts/link_check.py   --vault {vault}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
