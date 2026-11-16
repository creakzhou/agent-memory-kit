#!/usr/bin/env python3
"""A/B test: does the discipline layer change what the agent actually answers?

The claim every memory framework makes is "your agent remembers". The falsifiable
version is narrower: with the context file injected, the agent answers questions
about *your* conventions correctly; with it removed, it cannot. If both conditions
score the same, the file is decoration and should be deleted.

On Pi the switch is `-nc` / `--no-context-files`, which skips AGENTS.md and
CLAUDE.md entirely. On other hosts the equivalent is running the same prompt in a
directory without those files, which is what this script does for them: it feeds
the file in as context itself, so the comparison does not depend on the host.

Design notes
------------
* Only two conditions, no "base model" mystery condition. `ctx` = the file is in
  the prompt. `nc` = it is not.
* Scoring is regex, not judgement. Every question lists phrases that only appear
  in the discipline layer or vault contract, plus phrases that indicate the model
  is inventing an answer. Same rubric for both conditions.
* Exit 3 means "no gap" — the harness refuses to call a decoration a win.

Usage
-----
    python3 scripts/ab_context.py --discipline examples/MEMORY.md \
        --index examples/demo-vault/00-index.md --dry-run

    python3 scripts/ab_context.py --discipline examples/MEMORY.md \
        --index examples/demo-vault/00-index.md --agent ollama --model qwen2.5:7b

    python3 scripts/ab_context.py ... --engine stub-echo    # self-test only
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Rubric. `must` = at least one alternative must appear (case-insensitive).
# `forbid` = none may appear. Every `must` phrase is copied from the text that
# the scaffolder generates, so it cannot be answered from general knowledge.
# ---------------------------------------------------------------------------
RUBRIC = [
    {
        "id": "budget",
        "q": "The memory rules file has a hard character budget. What does the host do when that budget is exceeded?",
        "must": [r"injects? nothing", r"no truncat", r"does not truncat", r"nothing at all"],
        "forbid": [r"truncated to fit", r"silently truncat"],
        "why": "the file itself states the overflow behaviour; nobody guesses this",
    },
    {
        "id": "decisions",
        "q": "Where do decisions with their reasons get written, and may an old decision be rewritten?",
        "must": [r"04-decisions", r"04 decisions"],
        "forbid": [r"rewrit\w* (is|are) fine", r"safe to overwrite"],
        "why": "a numbered prefix invented by this layout",
    },
    {
        "id": "read-budget",
        "q": "How many notes should be read before concluding the index is wrong?",
        "must": [r"\bthree\b", r"\b3\b notes"],
        "forbid": [],
        "why": "counter-intuitive cap; a generic answer says 'as many as needed'",
    },
    {
        "id": "archive",
        "q": "Which prefix holds finished or dead work?",
        "must": [r"10-archive", r"10 archive"],
        "forbid": [],
        "why": "another invented prefix",
    },
    {
        "id": "split",
        "q": "A note seems to need two titles. What do you do?",
        "must": [r"two notes", r"split into two", r"separate notes"],
        "forbid": [],
        "why": "a specific editorial rule, not a default behaviour",
    },
    {
        "id": "no-hallucination",
        "q": "What storage does this memory system use?",
        "must": [r"markdown", r"plain text", r"files on disk", r"text files"],
        "forbid": [r"postgres", r"pinecone", r"vector database", r"sqlite", r"mongodb"],
        "why": "the trap: without context the model invents a database",
    },
]

# Non-interactive invocation per host. Flags are the ones documented at the time
# of writing; `--dry-run` exists precisely so they can be eyeballed before a run,
# and `--cmd` overrides everything if a host changes its interface.
ENGINES = {
    # Pi: -p = print mode (one shot), -nc = skip AGENTS.md / CLAUDE.md
    "pi": {"bin": "pi", "oneshot": ["-p"], "no_context": ["-nc"]},
    "claude": {"bin": "claude", "oneshot": ["-p"], "no_context": []},
    "codex": {"bin": "codex", "oneshot": ["exec"], "no_context": []},
    "gemini": {"bin": "gemini", "oneshot": ["-p"], "no_context": []},
    "ollama": {"bin": "ollama", "oneshot": ["run"], "no_context": [], "model_positional": True},
}

CONTEXT_HEADER = (
    "The following are your standing rules, injected as a context file before "
    "this conversation. Use them.\n\n--- BEGIN CONTEXT ---\n{body}\n--- END CONTEXT ---\n\n"
)


def load_rubric(path: str | None) -> list[dict]:
    if not path:
        return RUBRIC
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit("rubric must be a non-empty JSON array")
    for item in data:
        for key in ("id", "q", "must"):
            if key not in item:
                raise SystemExit(f"rubric entry missing '{key}': {item}")
        item.setdefault("forbid", [])
    return data


def build_context(files: list[tuple[Path | None, str]]) -> str:
    """One text block per file, in the order the host would inject them.

    On Pi, working inside the vault means three files are in play: the global
    discipline file, the vault's own AGENTS.md contract, and the index the
    contract points at. Passing all three is what `-nc` would remove at once.
    """
    parts = []
    for p, label in files:
        if p and Path(p).is_file():
            parts.append(f"<!-- {label}: {Path(p).name} -->\n{Path(p).read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def make_prompt(question: str, context: str, with_context: bool) -> str:
    body = ""
    if with_context:
        if not context.strip():
            raise SystemExit("--discipline/--index produced no text; nothing to inject")
        body = CONTEXT_HEADER.format(body=context)
    return (
        f"{body}Question: {question}\n\n"
        "Answer in one or two sentences. If the information is not available to "
        "you, say exactly 'not available' instead of guessing."
    )


def run_engine(engine: str, prompt: str, args, with_context: bool) -> str:
    """Return the agent's answer. `stub-*` engines exist only for self-tests."""
    if engine == "stub-echo":
        # Plausible stand-in for "context injection works": it repeats what it was
        # given and knows nothing otherwise. It never sees the rubric.
        return prompt if with_context else "not available"
    if engine == "stub-silent":
        # Negative control: always answers generically, so the harness must
        # report "no gap" rather than inventing one.
        return "not available"

    if engine == "custom":
        cmd = args.cmd
        if not cmd:
            raise SystemExit("--engine custom needs --cmd")
        proc = subprocess.run(
            cmd, shell=True, input=prompt, capture_output=True, text=True,
            timeout=args.timeout, cwd=args.cwd,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"agent failed ({proc.returncode}): {proc.stderr[:400]}")
        return proc.stdout

    spec = ENGINES[engine]
    if not shutil.which(spec["bin"]):
        raise SystemExit(
            f"'{spec['bin']}' is not installed. Run this on a host that has it, "
            f"or pass --engine custom --cmd '...' to plug in your own one-shot CLI."
        )
    argv = [spec["bin"], *spec["oneshot"]]
    if spec.get("model_positional"):
        if not args.model:
            raise SystemExit(f"--engine {engine} needs --model")
        argv.append(args.model)
    elif args.model:
        argv += ["--model", args.model]
    if not with_context:
        argv += spec["no_context"]
    proc = subprocess.run(
        argv, input=prompt, capture_output=True, text=True,
        timeout=args.timeout, cwd=args.cwd,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"agent failed ({proc.returncode}): {proc.stderr[:400]}")
    return proc.stdout


def score(answer: str, item: dict) -> dict:
    low = answer.lower()
    hits = [pat for pat in item["must"] if re.search(pat, low)]
    traps = [pat for pat in item["forbid"] if re.search(pat, low)]
    return {"hit": bool(hits), "trap": bool(traps), "matched": hits, "trapped": traps}


def dry_run(engine: str, args) -> int:
    spec = ENGINES.get(engine)
    print(f"engine   {engine}")
    if engine in ("stub-echo", "stub-silent"):
        print("command  (in-process stub, no subprocess)")
    elif engine == "custom":
        print(f"command  {args.cmd}   < prompt on stdin")
    elif spec:
        argv = [spec["bin"], *spec["oneshot"]]
        if spec.get("model_positional"):
            argv.append(args.model or "<model>")
        elif args.model:
            argv += ["--model", args.model]
        print(f"command  {' '.join(argv)}   < prompt on stdin")
        print(f"nc flag  {' '.join(spec['no_context']) or '(none — run in a dir without context files)'}")
        print(f"found    {shutil.which(spec['bin']) or 'NOT INSTALLED'}")
    for item in load_rubric(args.rubric):
        print(f"  [{item['id']:16}] {item['q'][:70]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="A/B the discipline layer: injected vs not.")
    ap.add_argument("--discipline", help="discipline file (MEMORY.md / AGENTS.md / CLAUDE.md)")
    ap.add_argument("--index", help="index note, injected alongside it")
    ap.add_argument("--extra", action="append", default=[], metavar="PATH",
                    help="another context file the host would inject (repeatable)")
    ap.add_argument("--engine", default="pi",
                    choices=[*ENGINES, "custom", "stub-echo", "stub-silent"])
    ap.add_argument("--model", help="model name, when the host needs one")
    ap.add_argument("--cmd", help="override the whole command; prompt arrives on stdin")
    ap.add_argument("--rubric", help="JSON file replacing the built-in rubric")
    ap.add_argument("--repeat", type=int, default=1, help="runs per cell (default 1)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--cwd", help="working directory for the agent")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", metavar="PATH", help="write a README-ready table")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rubric = load_rubric(args.rubric)
    if args.dry_run:
        return dry_run(args.engine, args)

    disc = Path(args.discipline).expanduser() if args.discipline else None
    idx = Path(args.index).expanduser() if args.index else None
    if disc and not disc.is_file():
        raise SystemExit(f"discipline file not found: {disc}")
    files = [(disc, "MEMORY RULES"), *[(Path(e).expanduser(), "CONTEXT") for e in args.extra],
             (idx, "VAULT INDEX")]
    context = build_context(files)

    rows = []
    for item in rubric:
        row = {"id": item["id"], "q": item["q"], "why": item.get("why", "")}
        for cond, with_ctx in (("ctx", True), ("nc", False)):
            hits = traps = 0
            answers = []
            for _ in range(max(1, args.repeat)):
                prompt = make_prompt(item["q"], context, with_ctx)
                ans = run_engine(args.engine, prompt, args, with_ctx)
                s = score(ans, item)
                hits += 1 if s["hit"] else 0
                traps += 1 if s["trap"] else 0
                answers.append(ans.strip()[:300])
            n = max(1, args.repeat)
            row[cond] = {"hit": hits == n, "trap": traps > 0, "rate": f"{hits}/{n}",
                         "answer": answers[0]}
        rows.append(row)

    ctx_hits = sum(1 for r in rows if r["ctx"]["hit"] and not r["ctx"]["trap"])
    nc_hits = sum(1 for r in rows if r["nc"]["hit"] and not r["nc"]["trap"])
    ctx_traps = sum(1 for r in rows if r["ctx"]["trap"])
    nc_traps = sum(1 for r in rows if r["nc"]["trap"])
    gap = ctx_hits > nc_hits
    report = {
        "engine": args.engine,
        "model": args.model,
        "notes": len(rubric),
        "ctx_correct": ctx_hits,
        "nc_correct": nc_hits,
        "ctx_traps": ctx_traps,
        "nc_traps": nc_traps,
        "gap": gap,
        "rows": rows,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"engine {args.engine}" + (f" / {args.model}" if args.model else ""))
        print(f"{'id':16} {'ctx':>4} {'nc':>4}  why it discriminates")
        for r in rows:
            mark = lambda c: "ok" if r[c]["hit"] and not r[c]["trap"] else ("TRAP" if r[c]["trap"] else "--")
            print(f"{r['id']:16} {mark('ctx'):>4} {mark('nc'):>4}  {r['why']}")
        print()
        print(f"correct:  ctx {ctx_hits}/{len(rows)}   nc {nc_hits}/{len(rows)}")
        print(f"traps:    ctx {ctx_traps}   nc {nc_traps}")
        print()
        if gap:
            print(f"VERDICT  GAP — the discipline layer is doing work "
                  f"({ctx_hits} vs {nc_hits} of {len(rows)}).")
        else:
            print("VERDICT  NO GAP — with and without the file score the same.")
            print("         Either every question is answerable from general")
            print("         knowledge (rubric too easy), or the file carries nothing")
            print("         the agent needs. Do not report this as a win.")

    if args.markdown:
        lines = [
            "| Question | With context file | With `-nc` |",
            "|---|---|---|",
        ]
        for r in rows:
            cell = lambda c: ("correct" if r[c]["hit"] and not r[c]["trap"]
                              else ("invented" if r[c]["trap"] else "not answered"))
            lines.append(f"| {r['q']} | {cell('ctx')} | {cell('nc')} |")
        lines.append("")
        lines.append(f"`{ctx_hits}/{len(rows)}` vs `{nc_hits}/{len(rows)}` correct · "
                     f"engine `{args.engine}`" + (f" · model `{args.model}`" if args.model else ""))
        Path(args.markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"markdown -> {args.markdown}")

    return 0 if gap else 3


if __name__ == "__main__":
    sys.exit(main())
