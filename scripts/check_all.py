#!/usr/bin/env python3
"""
check_all.py — Run every audit and print one summary.

Four checks, one exit code. Drops into CI or a pre-commit hook unchanged.

Usage:
    python3 scripts/check_all.py --config ./memory.config.json --vault ~/memory-vault
    python3 scripts/check_all.py --config ./memory.config.json --vault ~/memory-vault --identity ./identity.md
    python3 scripts/check_all.py --config ./memory.config.json --vault ~/memory-vault --json

Exit code 1 if any check fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, args: list) -> tuple:
    cmd = [sys.executable, str(HERE / script), *args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"ok": False, "reason": (proc.stderr or proc.stdout or "no output").strip()[:200]}
    return proc.returncode, data


def fmt_link(d: dict) -> str:
    if "dangling" not in d:
        return d.get("reason", "failed")
    return f"{len(d['dangling'])} dangling / {d['note_count']} notes, {d['link_count']} links"


def fmt_budget(d: dict) -> str:
    if "chars" not in d:
        return d.get("reason", "failed")
    return f"{d['chars']} / {d['effective_cap']} chars ({d['usage_pct']}%), headroom {d['headroom']:+d}"


def fmt_false_green(d: dict) -> str:
    if "scores" not in d:
        return d.get("reason", "failed")
    real = d["scores"]["real"]
    bad = d["scores"]["garbled"] + d["scores"]["negative"]
    best_real = max((s for _, s in real), default=0.0)
    worst_bad = max((s for _, s in bad), default=0.0)
    return (f"real best {best_real:.2f} / garbage best {worst_bad:.2f}, "
            f"window {d['safe_low']:.2f}-{d['t_real']:.2f}" if d["safe_window"] else
            f"no safe window, real best {best_real:.2f} / garbage best {worst_bad:.2f}")


def fmt_dup(d: dict) -> str:
    if "pairs" not in d:
        return d.get("reason", "failed")
    flagged = d["flagged"]
    if not flagged:
        return f"{len(d['pairs'])} layer pairs compared, none above {int(d['threshold']*100)}%"
    return ", ".join(f"{p['a']}->{p['b']} {p['content_of_a_in_b']*100:.0f}%" for p in flagged)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all memory audits.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--identity", help="optional identity layer file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg_path = Path(args.config).expanduser().resolve()
    if not cfg_path.is_file():
        print(f"error: config not found: {cfg_path}", file=sys.stderr)
        return 2

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    discipline = cfg.get("discipline_file")
    if discipline and not Path(discipline).is_absolute():
        discipline = str(cfg_path.parent / discipline)

    checks = []

    rc, d = run("link_check.py", ["--vault", args.vault])
    checks.append({"name": "link", "ok": bool(d.get("ok")), "detail": fmt_link(d), "rc": rc,
                   "fix": "delete or create the notes named in dangling[]"})

    if discipline:
        rc, d = run("budget_check.py", ["--file", str(discipline),
                                        "--budget", str(cfg.get("discipline_budget_chars", 3800))])
        checks.append({"name": "budget", "ok": bool(d.get("ok")), "detail": fmt_budget(d), "rc": rc,
                       "fix": "merge duplicates, move examples to a note, keep one pointer"})
    else:
        checks.append({"name": "budget", "ok": False, "detail": "no discipline_file in config",
                       "rc": 2, "fix": "run scaffold.py first"})

    rc, d = run("false_green.py", ["--vault", args.vault])
    checks.append({"name": "false-green", "ok": bool(d.get("ok")), "detail": fmt_false_green(d),
                   "rc": rc, "fix": "retitle notes by conclusion; fix the index summaries"})

    dup_args = ["--discipline", str(discipline)] if discipline else []
    if args.identity:
        dup_args += ["--identity", args.identity]
    if dup_args:
        rc, d = run("layer_dup.py", [*dup_args, "--vault", args.vault])
        checks.append({"name": "layer-dup", "ok": bool(d.get("ok")), "detail": fmt_dup(d), "rc": rc,
                       "fix": "keep the rule in one layer, leave a pointer in the other"})
    else:
        checks.append({"name": "layer-dup", "ok": False, "detail": "skipped, no discipline file",
                       "rc": 2, "fix": "run scaffold.py first"})

    all_ok = all(c["ok"] for c in checks)

    if args.json:
        print(json.dumps({"ok": all_ok, "checks": checks}, indent=2))
        return 0 if all_ok else 1

    print("=" * 70)
    print("MEMORY AUDIT")
    print("=" * 70)
    for c in checks:
        status = "PASS" if c["ok"] else "FAIL"
        print(f"  {c['name']:<12} {status:<5} {c['detail']}")
        if not c["ok"]:
            print(f"  {'':<12}       fix: {c['fix']}")
    print("-" * 70)
    passed = sum(1 for c in checks if c["ok"])
    print(f"  {passed}/{len(checks)} passed")
    print("")
    if all_ok:
        print("VERDICT  all checks pass. Now put real notes in the vault — structure")
        print("         without content proves nothing.")
    else:
        print("VERDICT  fix the failures above before trusting this setup.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
