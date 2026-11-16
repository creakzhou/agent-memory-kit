---
name: agent-memory-kit
display_name: "跨 Agent 记忆系统搭建与体检"
display_name_en: "Cross-Agent Memory Kit"
version: "1.0.0"
description_zh: >-
  为用户搭一套「会话关掉、换个 Agent、换台电脑都还在」的三层记忆系统（身份 / 纪律 / 事实），
  并且用脚本证明它真的生效，而不是假设它生效。适用场景：希望 AI 跨会话记住事情、要建记忆库或
  记忆文件夹、想让两个 Agent 共用同一份记忆、或想体检已有记忆系统是否存在失效指针、注入预算溢出、
  规则跨层重复、召回假绿。附带四个可离线运行的检查器与一组 A/B 对照实验脚本。不适用：存密钥、
  搭向量数据库、做笔记软件的界面。
description_en: >-
  Scaffold and audit a three-layer, cross-agent memory system (identity / discipline /
  facts) on the user's own machine. Use when the user wants their agent to remember
  across sessions, asks to set up a memory vault or memory folder, wants to share memory
  between two agents, or wants an existing memory setup audited for dangling pointers,
  budget overflow, duplicated layers, or false-green recall. Ships four offline checkers
  and an A/B harness that measures whether the rules actually change behaviour. Not for
  storing secrets, not for building a vector database, and not for note-taking UI work.
description: Scaffold and audit a three-layer, cross-agent memory system (identity / discipline / facts) on the user's own machine. Use when the user wants their agent to remember across sessions, asks to set up a memory vault or memory folder, wants to share memory between two agents, or wants an existing memory setup audited for dangling pointers, budget overflow, duplicated layers, or false-green recall. Not for storing secrets, not for building a vector database, and not for note-taking UI work.
---

# agent-memory-kit

Build the user a memory system that survives a closed session, an agent switch, and a
machine switch — then prove it works instead of assuming it.

## 0. Capability boundary — read before promising anything

These four facts decide what is honest to say. Violating them produces a system the
user will trust for a week and abandon after that.

1. **Auto-recall needs a host lifecycle hook.** Claude Code and DSH have one. Pi has
   the mechanism but no hook installed: it takes a TypeScript extension in
   `~/.pi/agent/extensions/`, written before anything is recalled. WorkBuddy, Codex,
   Cursor, and Gemini CLI have none at all. On those hosts recall is manual or
   tool-call triggered. Never describe it as "fully automatic".
2. **MCP is not a hook.** An MCP memory server exposes `search_memory` / `add_message`.
   Nothing reaches the context unless a tool is called. A configured MCP server proves
   a channel exists, not that recall happens.
3. **The identity layer belongs to the host.** If the platform has no cloud/profile
   memory, the identity layer collapses into the top of the discipline file, and the
   "follows the account" property is lost. Say so.
4. **You cannot generate the user's facts.** You generate structure. An empty vault with
   perfect structure is worth nothing until notes go in it.

## 1. Flow

Run these in order. Step 2 is a stop-and-confirm gate.

### Step 1 — Probe

```bash
python3 scripts/probe.py --out env.probe.json
```

Reads: installed agents, rule files already present, hook support and configuration,
MCP server counts, skills directories, write permissions.

Do not guess a platform from the user's wording. The probe is the source of truth.

### Step 2 — Report and confirm (stop here)

Show the user a table of four rows, in their language:

| Capability | Status | Consequence if missing |
|---|---|---|
| file read/write | yes/no | no vault, degrade to a pasteable memory card |
| lifecycle hook | yes/no/not configured | no auto-recall, manual triggers instead |
| MCP servers | count | no shared layer, use a folder or git |
| second agent | yes/no | single-machine setup, skip the shared layer |

Add one line stating the **actual** recall mode. Then stop and wait. Do not scaffold
before the user confirms — the target path and the layer split are their decision.

### Step 3 — Scaffold

```bash
python3 scripts/scaffold.py --target <vault> --rules-dir <project root> \
    --name "<user name>" --probe env.probe.json
```

Writes:
- the fact-layer vault (`00-index.md`, numbered folders, `AGENTS.md` contract, note template)
- the discipline file, with the filename the detected platform actually reads
- `memory.config.json`

Idempotent. Existing files are skipped unless `--force`.

### Step 4 — Wire the layers

Fill in the discipline file. Three blocks only:

- **Who I work for** — name, language, output shape, hard red lines. Under 10 lines.
- **How to use memory** — grep the index first, read at most three notes, say "no prior
  context" when recall is empty instead of inventing history.
- **Pointer block** — one line per topic pointing at a real note in the vault.

If the host has hooks, add the hook snippet now. If it does not, keep the manual-recall
block that `scaffold.py` generated and do not delete it to look tidier.

### Step 5 — Audit

```bash
python3 scripts/check_all.py --config ./memory.config.json --vault <vault>
```

Four checks, all must pass:

| Check | Failure means |
|---|---|
| link | a pointer resolves to nothing — the discipline file is teaching the agent to ignore it |
| budget | over the injection cap — the host injects **nothing**, not a truncation |
| false-green | no threshold separates real queries from garbage |
| layer-dup | the same fact lives in two layers and will drift |

Report raw numbers, not verdicts. "3 of 3 dangling links fixed, 2,412 / 3,610 chars,
real 0.18 vs garbage 0.00" is a result. "All checks passed" is not.

### Step 6 — Prove it (optional, on Pi it is one flag)

Offer this, do not force it. `-nc` on Pi loads no context files, which makes the
discipline layer testable rather than assumed:

```bash
python3 scripts/ab_context.py --discipline <rules>/AGENTS.md \
  --extra <vault>/AGENTS.md --index <vault>/00-index.md \
  --engine pi --repeat 3 --markdown AB-RESULT.md
```

- Exit 0 = a gap exists (with the file scores higher than without).
- Exit 3 = **no gap**. Say so. Do not soften it into "mostly working".
- Never report the result without the `-nc` column. A single-condition score
  proves nothing about the file.

If the host has no equivalent switch, run the same script: it injects the file
itself for the `ctx` condition, so the comparison still holds.

## 2. Commands

```bash
python3 scripts/probe.py        [--json] [--out env.probe.json]
python3 scripts/scaffold.py     --target <vault> [--rules-dir .] [--platform ID] [--dry-run] [--force]
python3 scripts/link_check.py   --vault <vault> [--include-templates]
python3 scripts/budget_check.py --config memory.config.json | --file X.md --budget N
python3 scripts/false_green.py  --vault <vault> [--top 5] [--step 0.05]
python3 scripts/layer_dup.py    --discipline X.md --vault <vault> [--identity Y.md]
python3 scripts/check_all.py    --config memory.config.json --vault <vault>
python3 scripts/ab_context.py   --discipline X.md [--extra Y] [--index Z] --engine pi|claude|codex|gemini|ollama|custom [--dry-run]
```

All scripts exit non-zero on failure. All accept `--json`.

## 3. Hard rules

- **One topic per note. Titles state the conclusion, not the topic word.**
- **A note not listed in `00-index.md` does not exist.** Folder browsing is not retrieval.
- **Grep the index before reading anything.** Reading the whole vault burns the budget
  that the discipline layer needs.
- **A pointer must resolve.** Run `link_check.py` after every rename or delete.
- **Never duplicate a rule across layers.** Keep the full text in one place, leave a
  pointer in the other. Copies drift, and a drifted copy looks as authoritative as the
  original.
- **Never count recall rows as proof.** Record the score of a negative control instead.
- **Never write secrets into the discipline file.** It is injected into every session.

## 4. What to tell the user

Give them, in this order:

1. What the probe found (four-row table).
2. What layer went where, with absolute paths.
3. The actual recall mode, in plain words: automatic / hook-capable but off / manual.
4. The audit numbers.
5. The one thing that will break first: usually either the budget filling up or the
   index falling out of sync. Name it so they watch for it.

Do not end with "let me know if you need anything else". End with the next concrete
action — usually "add three real notes and re-run the audit".
