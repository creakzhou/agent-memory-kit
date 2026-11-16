#!/usr/bin/env python3
"""
probe.py — Detect what memory capabilities the local agent environment actually has.

Zero dependencies. Python 3.8+.

The point of this script is to stop guessing. Most "agent memory" advice assumes
your agent can write files, run hooks, and reach an MCP server. That is true for
some hosts and false for others. This script produces an honest capability matrix
so the scaffolder can degrade instead of pretending.

Usage:
    python3 scripts/probe.py                 # human readable report
    python3 scripts/probe.py --json          # machine readable
    python3 scripts/probe.py --json --out env.probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()


# ---------------------------------------------------------------------------
# Platform registry
#
# Every entry describes where a given agent keeps its rule file, whether it can
# run hooks, and where it reads MCP servers from. Add a row here to support a
# new agent; nothing else in the codebase needs to change.
# ---------------------------------------------------------------------------

PLATFORMS = [
    {
        "id": "claude-code",
        "label": "Claude Code",
        "detect_dirs": [HOME / ".claude"],
        "detect_env": ["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"],
        "rule_file": "CLAUDE.md",
        "global_rule": HOME / ".claude" / "CLAUDE.md",
        "hooks": {
            "supported": True,
            "config": HOME / ".claude" / "settings.json",
            "note": "PreToolUse / PostToolUse / UserPromptSubmit / SessionStart",
        },
        "mcp_configs": [HOME / ".claude.json", Path(".mcp.json"), HOME / ".claude" / "mcp.json"],
        "skills_dir": HOME / ".claude" / "skills",
    },
    {
        "id": "codex",
        "label": "Codex CLI",
        "detect_dirs": [HOME / ".codex"],
        "detect_env": ["CODEX_HOME", "CODEX_SANDBOX"],
        "rule_file": "AGENTS.md",
        "global_rule": HOME / ".codex" / "AGENTS.md",
        "hooks": {"supported": False, "config": None, "note": "no lifecycle hooks"},
        "mcp_configs": [HOME / ".codex" / "config.toml"],
        "skills_dir": None,
    },
    {
        "id": "workbuddy",
        "label": "WorkBuddy / CodeBuddy",
        "detect_dirs": [HOME / ".workbuddy"],
        "detect_env": ["CODEBUDDY_MCP_CONFIG", "WORKBUDDY_HOME"],
        "rule_file": "AGENTS.md",
        "global_rule": HOME / ".workbuddy" / "memory" / "MEMORY.md",
        "hooks": {
            "supported": False,
            "config": None,
            "note": "MCP is tool-call style, not an auto-injected hook",
        },
        "mcp_configs": [HOME / ".workbuddy" / "mcp.json"],
        "skills_dir": HOME / ".workbuddy" / "skills",
    },
    {
        "id": "dsh",
        "label": "DSH (DeepSeek Harness)",
        "detect_dirs": [HOME / ".dsh", HOME / ".deepseek-harness"],
        "detect_env": ["DSH_HOME"],
        "rule_file": "AGENTS.md",
        "global_rule": HOME / ".dsh" / "AGENTS.md",
        "hooks": {
            "supported": True,
            "config": HOME / ".dsh",
            "note": "lifecycle plugin: before_prompt_build / agent_end",
        },
        "mcp_configs": [HOME / ".dsh" / "mcp.json"],
        "skills_dir": None,
    },
    {
        "id": "cursor",
        "label": "Cursor",
        "detect_dirs": [HOME / ".cursor", Path(".cursor")],
        "detect_env": ["CURSOR_TRACE_ID"],
        "rule_file": ".cursor/rules/memory.mdc",
        "global_rule": HOME / ".cursor" / "rules",
        "hooks": {"supported": False, "config": None, "note": "no lifecycle hooks"},
        "mcp_configs": [Path(".cursor") / "mcp.json", HOME / ".cursor" / "mcp.json"],
        "skills_dir": None,
    },
    {
        "id": "gemini-cli",
        "label": "Gemini CLI",
        "detect_dirs": [HOME / ".gemini"],
        "detect_env": ["GEMINI_CLI"],
        "rule_file": "GEMINI.md",
        "global_rule": HOME / ".gemini" / "GEMINI.md",
        "hooks": {"supported": False, "config": None, "note": "no lifecycle hooks"},
        "mcp_configs": [HOME / ".gemini" / "settings.json"],
        "skills_dir": None,
    },
    {
        "id": "generic",
        "label": "Any other agent (manual)",
        "detect_dirs": [],
        "detect_env": [],
        "rule_file": "AGENTS.md",
        "global_rule": None,
        "hooks": {"supported": False, "config": None, "note": "manual paste only"},
        "mcp_configs": [Path(".mcp.json")],
        "skills_dir": None,
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def expand(p) -> Path:
    return Path(os.path.expanduser(str(p)))


def count_mcp_servers(path: Path) -> tuple:
    """Best effort count of configured MCP servers. Never raises."""
    if not path.is_file():
        return 0, "missing"
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, "unreadable"

    if path.suffix == ".toml":
        n = raw.count("[mcp_servers.")
        return n, "ok"

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 0, "unparsable"

    for key in ("mcpServers", "mcp_servers", "servers"):
        block = data.get(key)
        if isinstance(block, dict):
            return len(block), "ok"
    return 0, "no mcp block"


def hooks_configured(path) -> bool:
    if not path or not Path(path).is_file():
        return False
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError, ValueError):
        return False
    return bool(data.get("hooks"))


def find_existing_rule_files() -> list:
    """Rule files that already exist in the current working directory tree."""
    names = [
        "CLAUDE.md", "AGENTS.md", "MEMORY.md", "GEMINI.md",
        ".cursorrules", ".windsurfrules", ".github/copilot-instructions.md",
    ]
    found = []
    cwd = Path.cwd()
    for n in names:
        p = cwd / n
        if p.is_file():
            found.append({"path": str(p), "bytes": p.stat().st_size})
    rules_dir = cwd / ".cursor" / "rules"
    if rules_dir.is_dir():
        for p in sorted(rules_dir.glob("*.mdc")):
            found.append({"path": str(p), "bytes": p.stat().st_size})
    return found


def detect_agent(entry: dict) -> dict:
    evidence = []
    for d in entry["detect_dirs"]:
        if expand(d).exists():
            evidence.append(str(expand(d)))
    for v in entry["detect_env"]:
        if os.environ.get(v):
            evidence.append(f"env:{v}")

    mcp_hits = []
    for c in entry["mcp_configs"]:
        cp = expand(c)
        n, state = count_mcp_servers(cp)
        if cp.is_file():
            mcp_hits.append({"path": str(cp), "servers": n, "state": state})

    skills_dir = entry["skills_dir"]
    skills_count = 0
    if skills_dir and expand(skills_dir).is_dir():
        skills_count = len(
            [p for p in expand(skills_dir).iterdir() if p.is_dir() and not p.name.startswith(".")]
        )

    return {
        "id": entry["id"],
        "label": entry["label"],
        "detected": bool(evidence),
        "evidence": evidence,
        "rule_file": entry["rule_file"],
        "global_rule": str(expand(entry["global_rule"])) if entry["global_rule"] else None,
        "hooks": {
            "supported": entry["hooks"]["supported"],
            "configured": hooks_configured(entry["hooks"]["config"]),
            "note": entry["hooks"]["note"],
        },
        "mcp": mcp_hits,
        "mcp_total_servers": sum(m["servers"] for m in mcp_hits),
        "skills_dir": str(expand(skills_dir)) if skills_dir else None,
        "skills_count": skills_count,
    }


def build_report() -> dict:
    agents = [detect_agent(e) for e in PLATFORMS]
    live = [a for a in agents if a["detected"]]

    # Pick the primary host: the one that has the most evidence, ties broken by
    # the order in PLATFORMS (specific before generic).
    primary = max(live, key=lambda a: len(a["evidence"])) if live else agents[-1]

    writable_targets = []
    for cand in [Path.cwd(), HOME / "memory-vault"]:
        try:
            writable_targets.append({"path": str(cand), "writable": os.access(cand, os.W_OK)})
        except OSError:
            pass

    auto_recall = any(a["hooks"]["supported"] and a["hooks"]["configured"] for a in live)
    hook_capable = any(a["hooks"]["supported"] for a in live)
    shared_layer = any(a["mcp_total_servers"] > 0 for a in live)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {
            "os": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
            "cwd": str(Path.cwd()),
        },
        "agents": agents,
        "detected_agents": [a["id"] for a in live],
        "primary_agent": primary["id"],
        "existing_rule_files": find_existing_rule_files(),
        "write_targets": writable_targets,
        "capability_summary": {
            "file_io": True,  # if this script runs, the host can execute code
            "auto_recall_hook": auto_recall,
            "hook_capable": hook_capable,
            "mcp_available": shared_layer,
            "multi_agent": len(live) > 1,
        },
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def verdict(flag: bool, yes="YES", no="NO") -> str:
    return yes if flag else no


def render(report: dict) -> str:
    out = []
    add = out.append
    cap = report["capability_summary"]

    add("=" * 66)
    add("MEMORY ENVIRONMENT PROBE")
    add("=" * 66)
    add(f"os        {report['host']['os']} {report['host']['release']}")
    add(f"python    {report['host']['python']}")
    add(f"cwd       {report['host']['cwd']}")
    add("")

    add("-- capability summary " + "-" * 42)
    add(f"  file read/write ........ {verdict(cap['file_io'])}")
    add(f"  hook-capable host ...... {verdict(cap['hook_capable'])}"
        f"   (auto recall: {verdict(cap['auto_recall_hook'])})")
    add(f"  MCP servers reachable .. {verdict(cap['mcp_available'])}")
    add(f"  multiple agents ........ {verdict(cap['multi_agent'])}")
    add("")

    add("-- agents " + "-" * 54)
    for a in report["agents"]:
        mark = "*" if a["id"] == report["primary_agent"] else " "
        state = "detected" if a["detected"] else "not found"
        add(f" {mark} {a['label']:<26} {state}")
        if a["detected"]:
            add(f"     rule file      {a['rule_file']}")
            add(f"     hooks          supported={a['hooks']['supported']} "
                f"configured={a['hooks']['configured']}")
            if a["mcp"]:
                for m in a["mcp"]:
                    add(f"     mcp            {m['path']} ({m['servers']} servers)")
            if a["skills_count"]:
                add(f"     skills         {a['skills_count']} in {a['skills_dir']}")
    add("")

    if report["existing_rule_files"]:
        add("-- existing rule files in cwd " + "-" * 34)
        for f in report["existing_rule_files"]:
            add(f"   {f['path']}  ({f['bytes']} bytes)")
        add("")

    add("-- what this means " + "-" * 45)
    if cap["auto_recall_hook"]:
        add("  You can wire true automatic recall. Wire it.")
    elif cap["hook_capable"]:
        add("  A hook-capable host exists but no hook is configured yet.")
        add("  Scaffold will emit the hook snippet; you must enable it.")
    else:
        add("  No lifecycle hook available.")
        add("  Recall will be tool-call triggered, not automatic.")
        add("  Do not describe this setup as 'fully automatic' anywhere.")
    if not cap["mcp_available"]:
        add("  No MCP server configured: the shared layer must be a folder or a git repo.")
    add("")
    add("Next: python3 scripts/scaffold.py --probe env.probe.json")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe agent memory capabilities.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument("--out", help="write the report to this path")
    args = ap.parse_args()

    report = build_report()

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report))
        if args.out:
            print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
