#!/usr/bin/env python3
"""
false_green.py — Prove recall actually discriminates, instead of counting hits.

The failure everyone ships: "it returned 3 memories, so it works." Lower the
similarity threshold far enough and a garbage query also returns 3 memories.
Hit count is not evidence.

This runs a lexical recall (TF-IDF cosine over character bigrams) across a
threshold sweep and looks for a **safe operating window**: the band where real
queries still hit and garbled / negative-control queries hit nothing. If no such
band exists, the retrieval is decoration.

Scope — read this before quoting the result:
  Lexical recall is strict. Lexical passing does NOT prove your semantic backend
  passes. If your backend is an embedding service, run the same three query
  classes inside your agent and compare, because embeddings give non-zero
  similarity to strings that share no tokens at all. That is exactly how false
  green happens.

Usage:
    python3 scripts/false_green.py --vault ./vault
    python3 scripts/false_green.py --vault ./vault --json
    python3 scripts/false_green.py --vault ./vault --top 5 --step 0.05

Exit code 1 when no safe threshold window exists.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff]")
WORD = re.compile(r"[a-z0-9_]{2,}")

# Structurally normal topics that almost never exist in a personal vault. The
# script swaps any of these out if the vault happens to contain them.
NEGATIVE_POOL = [
    "供应商碳排放审计流程",
    "办公室搬迁预算审批",
    "董事会换届选举时间表",
    "marine insurance claim escalation",
    "warehouse forklift certification renewal",
    "quarterly dividend withholding procedure",
]

GARBLED = [
    "龘靐齉爩麤灪龖",
    "qzxv kjwp fflm vvbn",
]

# Templates and the vault contract are not retrievable notes.
SKIP_DIRS = {"90-templates", ".obsidian", ".git"}
SKIP_FILES = {"AGENTS.md"}


def tokenize(text: str) -> list:
    """CJK -> character bigrams; latin -> lowercase words. No external deps."""
    text = text.lower()
    toks = WORD.findall(text)
    chars = CJK.findall(text)
    for i in range(len(chars) - 1):
        toks.append(chars[i] + chars[i + 1])
    if len(chars) == 1:
        toks.append(chars[0])
    return toks


def build_index(docs: dict) -> tuple:
    tf = {}
    df = {}
    for name, text in docs.items():
        counts = {}
        for t in tokenize(text):
            counts[t] = counts.get(t, 0) + 1
        tf[name] = counts
        for t in counts:
            df[t] = df.get(t, 0) + 1

    n = len(docs)
    vecs = {}
    for name, counts in tf.items():
        vec = {}
        for t, c in counts.items():
            idf = math.log((n + 1) / (df[t] + 1)) + 1.0
            vec[t] = (1 + math.log(c)) * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vecs[name] = {t: v / norm for t, v in vec.items()}
    return vecs, df, n


def score(query: str, vecs: dict, df: dict, n: int) -> list:
    counts = {}
    for t in tokenize(query):
        counts[t] = counts.get(t, 0) + 1
    qvec = {}
    for t, c in counts.items():
        if t not in df:
            continue  # out-of-vocabulary contributes nothing
        idf = math.log((n + 1) / (df[t] + 1)) + 1.0
        qvec[t] = (1 + math.log(c)) * idf
    norm = math.sqrt(sum(v * v for v in qvec.values()))
    if not norm:
        return []
    qvec = {t: v / norm for t, v in qvec.items()}

    out = []
    for name, dvec in vecs.items():
        if len(qvec) < len(dvec):
            dot = sum(v * dvec.get(t, 0.0) for t, v in qvec.items())
        else:
            dot = sum(dvec[t] * qvec.get(t, 0.0) for t in dvec)
        out.append((name, dot))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def pick_real_queries(docs: dict, k: int = 3) -> list:
    """Use the note's own H1 as the query: if the vault cannot find its own
    titles, the titles are the problem, not the retriever."""
    names = []
    for name, text in docs.items():
        title = ""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if len(title) < 8:
            stem = Path(name).stem
            title = re.sub(r"^\d+[-_]", "", stem).replace("-", " ").replace("_", " ").strip()
        if len(title) >= 8 and not title.isdigit():
            names.append(title)
    random.Random(7).shuffle(names)
    return names[:k]


def pick_negative_queries(vecs, df, n, k: int = 3) -> list:
    """Keep only negatives that share no meaningful signal with the vault."""
    chosen = []
    for q in NEGATIVE_POOL:
        ranked = score(q, vecs, df, n)
        if not ranked or ranked[0][1] < 0.12:
            chosen.append(q)
        if len(chosen) == k:
            break
    return chosen


def best_score(query: str, vecs: dict, df: dict, n: int) -> float:
    """Score of the single best match: this is what a threshold actually gates on."""
    ranked = score(query, vecs, df, n)
    return ranked[0][1] if ranked else 0.0


def evaluate(vault: Path, top: int, step: float) -> dict:
    files = sorted(
        p for p in vault.rglob("*.md")
        if p.is_file()
        and p.name not in SKIP_FILES
        and not (set(p.relative_to(vault).parts[:-1]) & SKIP_DIRS)
    )
    docs = {}
    for p in files:
        rel = str(p.relative_to(vault))
        docs[rel] = p.read_text(encoding="utf-8", errors="ignore")[:8000]

    if len(docs) < 2:
        return {"ok": False, "reason": "vault needs at least 2 notes", "vault": str(vault)}

    vecs, df, n = build_index(docs)
    real = pick_real_queries(docs)
    neg = pick_negative_queries(vecs, df, n)
    garbled = list(GARBLED)

    if len(real) < 2:
        return {
            "ok": False,
            "reason": "fewer than 2 usable note titles — filenames must state the topic in 8+ characters",
            "vault": str(vault),
        }

    rows = []
    t = 0.05
    while t <= 0.85 + 1e-9:
        rows.append({
            "threshold": round(t, 2),
            "real_hits": sum(1 for q in real if best_score(q, vecs, df, n) >= t),
            "garbled_hits": sum(1 for q in garbled if best_score(q, vecs, df, n) >= t),
            "negative_hits": sum(1 for q in neg if best_score(q, vecs, df, n) >= t),
        })
        t += step

    total_real = len(real)
    t_false = next(
        (r["threshold"] for r in rows if r["garbled_hits"] + r["negative_hits"] > 0),
        None,
    )
    # A threshold is usable when every real query still hits and nothing false
    # does. The highest usable threshold is the recommendation: strictest
    # setting that keeps recall intact.
    safe_rows = [
        r for r in rows
        if r["real_hits"] >= total_real and r["garbled_hits"] + r["negative_hits"] == 0
    ]
    safe = bool(safe_rows)
    t_real = safe_rows[-1]["threshold"] if safe_rows else None
    safe_low = safe_rows[0]["threshold"] if safe_rows else None
    recommended = t_real

    return {
        "vault": str(vault),
        "notes": len(docs),
        "top_k": top,
        "queries": {"real": real, "garbled": garbled, "negative": neg},
        "scores": {
            "real": [[q, round(best_score(q, vecs, df, n), 3)] for q in real],
            "garbled": [[q, round(best_score(q, vecs, df, n), 3)] for q in garbled],
            "negative": [[q, round(best_score(q, vecs, df, n), 3)] for q in neg],
        },
        "sweep": rows,
        "t_real": t_real,
        "safe_low": safe_low,
        "t_false": t_false,
        "safe_window": safe,
        "recommended_threshold": recommended,
        "ok": safe,
    }


def render(r: dict) -> str:
    if "sweep" not in r:
        return f"FAIL — {r.get('reason', 'unknown')}"

    out = []
    add = out.append
    add("=" * 66)
    add("FALSE-GREEN CHECK  (lexical recall, TF-IDF cosine over char bigrams)")
    add("=" * 66)
    add(f"vault   {r['vault']}")
    add(f"notes   {r['notes']}   top_k {r['top_k']}")
    add("")
    add("queries — best-match score against the whole vault")
    for kind in ("real", "garbled", "negative"):
        for q, s in r["scores"][kind]:
            add(f"  {kind:<9} {s:>5.2f}  {q}")
    add("")
    add("threshold   real   garbled   negative")
    add("-" * 40)
    for row in r["sweep"]:
        mark = ""
        if row["garbled_hits"] + row["negative_hits"]:
            mark = "  <- false positives start"
        add(f"   {row['threshold']:.2f}     {row['real_hits']:>2}      "
            f"{row['garbled_hits']:>2}        {row['negative_hits']:>2}{mark}")
    add("")

    if r["safe_window"]:
        add("VERDICT  PASS — a safe operating window exists.")
        add(f"         safe window    {r['safe_low']:.2f} – {r['t_real']:.2f}"
            f"   (all {len(r['queries']['real'])} real queries hit, 0 false positives)")
        add(f"         false positives begin at "
            f"{r['t_false'] if r['t_false'] is not None else 'never in range'}")
        add(f"         recommended    {r['recommended_threshold']:.2f}"
            f"   (strictest threshold that keeps recall intact)")
        add("")
        add("         Absolute scores are low because the corpus is small. What")
        add("         matters is the gap: real queries score well above zero while")
        add("         garbage scores exactly zero. A narrow window is normal here;")
        add("         a window that does not exist at all is the failure.")
    else:
        add("VERDICT  FAIL — no threshold separates real from garbage.")
        add("         Either the notes are not titled by topic, or the index")
        add("         summaries are too generic. Fix the content, not the threshold.")
    add("")
    add("CAVEAT  This is lexical recall. An embedding backend can score garbage")
    add("        above 0.4 and still look fine. Run the same three query classes")
    add("        in your agent and record the raw numbers before claiming it works.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect false-green recall.")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.is_dir():
        print(f"error: vault not found: {vault}", file=sys.stderr)
        return 2

    report = evaluate(vault, args.top, args.step)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
