#!/usr/bin/env python3
"""
selftest.py — prove the audits are not rubber stamps.

A linter that only ever prints PASS is decoration. This script drives the whole
pipeline twice: once on clean input, where everything must pass, and once per
injected defect, where the specific check must fail. It also asserts that the
failure goes away when the defect is removed, so a green run cannot be explained
by a stale directory.

Runs offline, no dependencies, and is what CI executes. If this passes, the
scripts work; if it fails, they do not.

Usage:
    python3 scripts/selftest.py
    python3 scripts/selftest.py --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

RESULTS = []
VERBOSE = False


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def run(script: str, *args, env=None) -> tuple:
    cmd = [sys.executable, str(HERE / script), *[str(a) for a in args]]
    full_env = dict(os.environ)
    full_env.update(env or {})
    proc = subprocess.run(cmd, capture_output=True, text=True, env=full_env)
    if VERBOSE and proc.returncode != 0:
        print(f"      $ {script} {' '.join(str(a) for a in args)}  -> {proc.returncode}")
        for line in (proc.stdout + proc.stderr).strip().splitlines()[-6:]:
            print(f"        {line}")
    return proc.returncode, proc.stdout + proc.stderr


def case(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if detail and not ok:
        print(f"        {detail}")


def scaffold(root: Path, platform: str = "pi") -> tuple:
    """Build a vault + discipline layer and return (vault, discipline file)."""
    rc, out = run("scaffold.py", "--target", root / "vault", "--rules-dir", root,
                  "--name", "Self Test", "--platform", platform)
    cfg = json.loads((root / "memory.config.json").read_text(encoding="utf-8"))
    return root / "vault", Path(cfg["discipline_file"]), rc, out


def audit(root: Path) -> tuple:
    return run("check_all.py", "--config", root / "memory.config.json",
               "--vault", root / "vault")


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------

def test_scaffold_and_audit(tmp: Path) -> None:
    """Clean input must pass, or every later failure is meaningless."""
    root = tmp / "clean"
    root.mkdir()
    vault, discipline, rc, out = scaffold(root)
    case("scaffold writes a vault and a discipline file",
         rc == 0 and vault.is_dir() and discipline.is_file(),
         out.strip()[-300:])

    rc, out = audit(root)
    case("clean vault passes all four checks", rc == 0, out.strip()[-400:])


def test_dangling_link(tmp: Path) -> None:
    """A pointer to a note that does not exist must fail the audit."""
    root = tmp / "dangling"
    root.mkdir()
    vault, discipline, _, _ = scaffold(root)
    note = vault / "20-notes" / "pointer-probe.md"
    note.write_text("# Pointer probe\n\nSee [[a-note-that-never-existed]].\n",
                    encoding="utf-8")

    rc, out = audit(root)
    case("dangling wikilink fails the audit", rc == 1, f"exit {rc}\n{out[-300:]}")
    case("the failure names the link check", "link" in out and "FAIL" in out, out[-300:])

    note.unlink()
    rc, out = audit(root)
    case("removing the dangling link restores a green audit", rc == 0, out[-300:])


def test_budget_overflow(tmp: Path) -> None:
    """A discipline layer over the cap must fail, not get silently truncated."""
    root = tmp / "budget"
    root.mkdir()
    vault, discipline, _, _ = scaffold(root)
    original = discipline.read_text(encoding="utf-8")
    discipline.write_text(original + "\n" + "padding rule. " * 500, encoding="utf-8")

    rc, out = run("budget_check.py", "--file", discipline, "--budget", "3600")
    case("over-budget discipline fails", rc == 1, f"exit {rc}\n{out[-300:]}")
    case("the failure reports how far over it is", "over" in out.lower(), out[-300:])

    rc, _ = audit(root)
    case("check_all propagates the budget failure", rc == 1, "check_all returned 0")

    discipline.write_text(original, encoding="utf-8")
    rc, _ = audit(root)
    case("restoring the discipline file clears the failure", rc == 0)


def test_layer_duplication(tmp: Path) -> None:
    """The same rules copied into the vault must be flagged."""
    root = tmp / "dup"
    root.mkdir()
    vault, discipline, _, _ = scaffold(root)
    copy = vault / "20-notes" / "copied-rules.md"
    copy.write_text(discipline.read_text(encoding="utf-8"), encoding="utf-8")

    rc, out = run("layer_dup.py", "--discipline", discipline, "--vault", vault)
    case("rules duplicated into the vault fail", rc == 1, f"exit {rc}\n{out[-300:]}")

    copy.unlink()
    rc, _ = run("layer_dup.py", "--discipline", discipline, "--vault", vault)
    case("removing the copy clears the duplication", rc == 0)


def test_identity_inside_vault(tmp: Path) -> None:
    """An identity file that lives in the vault must not compare against itself.

    This was a real false positive: identity vs vault scored 100% simply because
    the identity file was one of the vault's notes.
    """
    root = tmp / "identity"
    root.mkdir()
    vault, discipline, _, _ = scaffold(root)
    identity = vault / "03-preferences" / "about-me.md"

    rc, out = run("layer_dup.py", "--discipline", discipline,
                  "--vault", vault, "--identity", identity)
    case("identity stored inside the vault is not self-compared", rc == 0,
         f"exit {rc}\n{out[-300:]}")


def test_false_green_contract(tmp: Path) -> None:
    """false_green must refuse to grade a vault it cannot discriminate."""
    root = tmp / "tiny"
    root.mkdir()
    tiny = root / "vault"
    tiny.mkdir()
    (tiny / "only-note.md").write_text("# Only note\n\nSome content.\n", encoding="utf-8")

    rc, out = run("false_green.py", "--vault", tiny)
    case("a one-note vault is refused instead of scored", rc == 1,
         f"exit {rc}\n{out[-300:]}")

    big = tmp / "clean" / "vault"
    rc, out = run("false_green.py", "--vault", big, "--json")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {}
    scores = data.get("scores") or {}
    real = [s for _, s in scores.get("real", [])]
    bad = [s for _, s in (scores.get("garbled", []) + scores.get("negative", []))]
    highest = max(real) if real else 0.0
    worst = max(bad) if bad else 0.0
    case("false_green verdict is consistent with its own numbers",
         bool(data) and (not data.get("ok") or highest > worst),
         f"json={out[-200:]}")


def test_pi_detection(tmp: Path) -> None:
    """Regression: Pi was added on the strength of its docs, so pin the facts.

    Pi reads AGENTS.md *and* CLAUDE.md from ~/.pi/agent/, and configures lifecycle
    behaviour with a directory of TypeScript extensions rather than a JSON block.
    """
    home = tmp / "fakepi"
    agent = home / ".pi" / "agent"
    (agent / "extensions").mkdir(parents=True)
    (agent / "skills" / "recall").mkdir(parents=True)
    (agent / "extensions" / "recall.ts").write_text("export default {};\n", encoding="utf-8")
    (agent / "mcp.json").write_text(
        json.dumps({"mcpServers": {"filesystem": {"command": "npx", "args": ["-y", "x"]}}}),
        encoding="utf-8")

    env = {"HOME": str(home), "USERPROFILE": str(home),
           "PI_CODING_AGENT_DIR": str(agent)}
    rc, out = run("probe.py", "--json", env=env)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        data = {}

    pi = next((a for a in data.get("agents", []) if a["id"] == "pi"), {})
    case("probe detects Pi from ~/.pi/agent", "pi" in data.get("detected_agents", []),
         out[-300:])
    case("Pi reports hook support with a configured extension dir",
         bool(pi.get("hooks", {}).get("supported")) and bool(pi.get("hooks", {}).get("configured")),
         json.dumps(pi.get("hooks", {})))
    case("Pi MCP servers are counted from mcp.json",
         pi.get("mcp_total_servers") == 1, json.dumps(pi.get("mcp")))
    case("probe repeats Pi's two-file loading quirk",
         "CLAUDE.md" in (pi.get("extra_note") or ""), str(pi.get("extra_note")))


def test_ab_context_contract(tmp: Path) -> None:
    """The A/B harness must report a gap when there is one and refuse when not.

    No model is involved: `stub-echo` repeats an injected context file (so the
    answers must score) and `stub-silent` answers generically (so nothing may
    score). If the second case ever reported a gap, the harness would be
    measuring itself instead of the agent — the exact failure this repo is built
    to catch elsewhere.
    """
    root = tmp / "ab"
    root.mkdir()
    vault, discipline, rc, out = scaffold(root)
    if rc != 0:
        case("A/B scaffold succeeds", False, out[-300:])
        return

    ctx = ["--discipline", discipline,
           "--extra", vault / "AGENTS.md",
           "--index", vault / "00-index.md"]

    rc, out = run("ab_context.py", *ctx, "--engine", "stub-echo")
    case("with the context file, a context-following agent scores every question",
         rc == 0 and "GAP" in out and "6/6" in out, f"exit {rc}\n{out[-400:]}")

    table = root / "table.md"
    rc, out = run("ab_context.py", *ctx, "--engine", "stub-echo", "--markdown", table)
    body = table.read_text(encoding="utf-8") if table.is_file() else ""
    # Cells now carry the agent's own words, which may contain "---" or a pipe.
    # Count unescaped pipes so a quoted answer cannot fake a column.
    rows = [ln for ln in body.splitlines()
            if ln.startswith("| ") and not re.fullmatch(r"\|[\s\-:|]+\|", ln)]
    case("markdown output is a three-column table with one row per question",
         rc == 0 and len(rows) == 7
         and all(r.replace("\\|", "").count("|") == 4 for r in rows),
         f"rows={len(rows)}\n{body[:300]}")
    case("the table records no fabricated result word",
         "correct" in body and "not answered" in body, body[:300])
    case("the table quotes what the agent actually answered",
         body.count('"') >= 12, "expected a quote in every cell")

    rc, out = run("ab_context.py", "--discipline", discipline, "--engine", "stub-silent")
    case("without any use of the context, the harness reports NO GAP and exits 3",
         rc == 3 and "NO GAP" in out, f"exit {rc}\n{out[-400:]}")

    # A real model hit this: a reasoning model spent its whole token budget on
    # chain-of-thought and printed an empty answer. Scoring that as "wrong" would
    # have produced a 6/0 table out of a broken engine — a false green of exactly
    # the kind this repo audits for.
    silent = f'"{sys.executable}" -c pass'
    rc, out = run("ab_context.py", "--discipline", discipline,
                  "--engine", "custom", "--cmd", silent)
    case("an engine that prints nothing aborts the run instead of scoring silence",
         rc != 0 and "empty output" in out, f"exit {rc}\n{out[-400:]}")

    rc, out = run("ab_context.py", "--discipline", discipline, "--engine", "pi", "--dry-run")
    case("dry-run prints the -nc switch instead of guessing it at runtime",
         rc == 0 and "-nc" in out, out[-300:])


def test_hygiene() -> None:
    """Guards against the mistake this repo already made once: shipping local paths."""
    # Split the literals so this file does not match its own scan.
    needles = ["/" + "Users/", "/" + "Volumes/", "C:" + "\\Users\\"]
    skip_dirs = {".git", "__pycache__", "node_modules", ".github"}
    offenders = []
    for p in REPO.rglob("*"):
        if not p.is_file() or any(part in skip_dirs for part in p.parts):
            continue
        if p.suffix not in {".md", ".py", ".json", ".tpl", ".yml", ".yaml", ".sh", ""}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in text for n in needles):
            offenders.append(str(p.relative_to(REPO)))

    case("no absolute home paths in tracked files", not offenders, ", ".join(offenders))

    stray = [p.name for p in REPO.rglob("env.probe.json")]
    case("no probe output committed", not stray, ", ".join(stray))

    skill = REPO / "SKILL.md"
    text = skill.read_text(encoding="utf-8") if skill.is_file() else ""
    # Parse to the closing --- rather than taking the first N characters: a
    # character window silently stops covering the field it looks for the moment
    # the frontmatter grows, and reports a missing key that is plainly there.
    block, keys = "", set()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        block = text[:end] if end != -1 else text
        keys = set(re.findall(r"(?m)^([A-Za-z_][\w-]*):", block))
    case("SKILL.md frontmatter declares a name and a description",
         {"name", "description"} <= keys, sorted(keys))
    case("SKILL.md carries the five fields the marketplace refuses without",
         {"version", "display_name", "display_name_en",
          "description_zh", "description_en"} <= keys, sorted(keys))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description="Self-test the memory audits.")
    ap.add_argument("--verbose", action="store_true", help="show command output on failure")
    args = ap.parse_args()
    VERBOSE = args.verbose

    print("=" * 70)
    print("SELFTEST — every check must pass on clean input and fail on dirty input")
    print("=" * 70)

    with tempfile.TemporaryDirectory(prefix="amk-selftest-") as td:
        tmp = Path(td)
        test_scaffold_and_audit(tmp)
        test_dangling_link(tmp)
        test_budget_overflow(tmp)
        test_layer_duplication(tmp)
        test_identity_inside_vault(tmp)
        test_false_green_contract(tmp)
        test_pi_detection(tmp)
        test_ab_context_contract(tmp)
        test_hygiene()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("-" * 70)
    print(f"  {passed}/{total} passed")
    if passed != total:
        print("\nFAILED:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name}")
                if detail:
                    print(f"    {detail[:400]}")
        return 1
    print("\nVERDICT  the audits discriminate. CI can trust them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
