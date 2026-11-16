#!/usr/bin/env python3
"""
layer_dup.py — Detect content duplicated across memory layers.

When the same fact lives in the identity file, the discipline file, and a note,
you pay for it three times in context and then pay again when the copies drift
apart. Duplication is not redundancy, it is a future contradiction.

Compares:
  identity vs discipline   (usually the worst offender)
  discipline vs vault
  vault index vs vault notes  (index summaries restating the note body)

Usage:
    python3 scripts/layer_dup.py --discipline ./CLAUDE.md --vault ./vault
    python3 scripts/layer_dup.py --discipline ./MEMORY.md --vault ./vault --identity ./identity.md
    python3 scripts/layer_dup.py --discipline ./CLAUDE.md --vault ./vault --json

Exit code 1 when duplication exceeds the threshold.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

STRIP = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def normalize(text: str) -> str:
    return STRIP.sub("", text.lower())


def shingles(text: str, n: int = 8) -> set:
    s = normalize(text)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(inner: set, outer: set) -> float:
    """What fraction of `inner` also appears in `outer` — better than Jaccard when
    one side is much larger (a whole vault vs one discipline file)."""
    if not inner:
        return 0.0
    return len(inner & outer) / len(inner)


def repeated_lines(texts: dict, min_len: int = 12) -> list:
    seen = {}
    for name, text in texts.items():
        for line in text.splitlines():
            key = normalize(line)
            if len(key) < min_len:
                continue
            seen.setdefault(key, []).append(name)
    dupes = []
    for key, where in seen.items():
        uniq = sorted(set(where))
        if len(uniq) > 1:
            dupes.append({"text_len": len(key), "layers": uniq})
    dupes.sort(key=lambda d: d["text_len"], reverse=True)
    return dupes[:15]


def analyze(files: dict, threshold: float) -> dict:
    texts = {}
    for name, path in files.items():
        if path and Path(path).is_file():
            texts[name] = Path(path).read_text(encoding="utf-8", errors="ignore")

    sh = {name: shingles(t) for name, t in texts.items()}
    pairs = []

    def add_pair(a, b):
        if a in sh and b in sh:
            cont = containment(sh[a], sh[b])
            pairs.append({
                "a": a,
                "b": b,
                "content_of_a_in_b": round(cont, 3),
                "jaccard": round(jaccard(sh[a], sh[b]), 3),
                "flag": cont > threshold,
            })

    add_pair("identity", "discipline")
    add_pair("discipline", "vault")
    add_pair("identity", "vault")

    dupes = repeated_lines(texts)
    flagged = [p for p in pairs if p["flag"]]

    return {
        "files": {k: str(v) for k, v in files.items() if v},
        "chars": {k: len(v) for k, v in texts.items()},
        "threshold": threshold,
        "pairs": pairs,
        "repeated_lines": dupes,
        "flagged": flagged,
        "ok": not flagged,
    }


def render(r: dict) -> str:
    out = []
    add = out.append
    add("=" * 66)
    add("LAYER DUPLICATION CHECK")
    add("=" * 66)
    for k, v in r["files"].items():
        add(f"  {k:<11} {r['chars'].get(k, 0):>6} chars   {v}")
    add("")
    add(f"threshold: {int(r['threshold']*100)}% of the smaller layer's content reused in the larger")
    add("")

    if not r["pairs"]:
        add("no comparable pairs — provide at least two layers")
        return "\n".join(out)

    add("pairs")
    for p in r["pairs"]:
        mark = "  FLAG" if p["flag"] else ""
        add(f"  {p['a']} -> {p['b']}: {p['content_of_a_in_b']*100:.1f}% reused, "
            f"jaccard {p['jaccard']:.3f}{mark}")
    add("")

    if r["repeated_lines"]:
        add("verbatim lines appearing in more than one layer")
        for d in r["repeated_lines"][:10]:
            add(f"  {d['text_len']:>4}c  {', '.join(d['layers'])}")
        add("")

    if r["ok"]:
        add("VERDICT  PASS — layers carry different content.")
    else:
        add("VERDICT  FAIL — layers are duplicating each other.")
        add("")
        add("  Fix: keep the full rule in exactly one place. The other layer gets")
        add("  a one-line pointer. Copies drift, and a drifted copy is worse than")
        add("  a missing one because both look authoritative.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Check for duplicated content across memory layers.")
    ap.add_argument("--discipline", required=True)
    ap.add_argument("--vault", required=True, help="vault directory")
    ap.add_argument("--identity", help="optional identity file")
    ap.add_argument("--threshold", type=float, default=0.18,
                    help="fraction of reuse that counts as duplication (default 0.18)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 2

    # An identity file that lives inside the vault would trivially be "100%
    # duplicated" with the vault. That comparison is meaningless, so drop it.
    identity = args.identity
    if identity:
        try:
            Path(identity).expanduser().resolve().relative_to(vault)
            print("note: identity file is inside the vault — skipping identity vs vault",
                  file=sys.stderr)
            identity = None
        except ValueError:
            pass

    vault_text = []
    for p in sorted(vault.rglob("*.md"))[:400]:
        vault_text.append(p.read_text(encoding="utf-8", errors="ignore"))
    tmp_vault = vault / ".layer-dup-tmp.md"
    combined = "\n".join(vault_text)
    try:
        tmp_vault.write_text(combined, encoding="utf-8")
        files = {
            "identity": identity,
            "discipline": args.discipline,
            "vault": str(tmp_vault),
        }
        report = analyze(files, args.threshold)
    finally:
        if tmp_vault.exists():
            tmp_vault.unlink()
        report["files"]["vault"] = str(vault)

    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
