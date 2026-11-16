# agent-memory-kit

**A scaffolder and linter for three-layer agent memory that survives session resets — and works across different agents.**

[![audit](https://github.com/creakzhou/agent-memory-kit/actions/workflows/audit.yml/badge.svg)](https://github.com/creakzhou/agent-memory-kit/actions/workflows/audit.yml)

Most "agent memory" projects ship a database or an SDK. This one ships the boring parts that actually decide whether memory works: a folder layout, a budget, a pointer contract, and four checks that catch the ways a memory system silently lies to you.

---

## The problem

Three things break memory, and they need three different fixes:

| Break | What happens | Fix |
|---|---|---|
| Session closes | Context evaporates | Facts persisted to a file tree, not to the context window |
| You switch agents | Next agent starts from zero | A shared, agent-agnostic fact layer |
| You switch machines | Memory file is not there | Memory that lives in a portable folder, plus a cloud identity layer |

One document cannot fix three breaks. That is why this is three layers, not one file.

## Three layers

| Layer | Holds | Where it lands | Budget |
|---|---|---|---|
| **L1 Identity** | who you are, tone, standing context | host cloud memory / system prompt | follows the account |
| **L2 Discipline** | hard rules, do-this-never-that | `CLAUDE.md` / `AGENTS.md` / `MEMORY.md` / `GEMINI.md` | 3,800 chars, hard |
| **L3 Facts** | what actually happened, decisions, reviews | plain markdown vault + index + wikilinks | unbounded, retrieved on demand |

Mixing them is the most common failure: identity text eats the discipline budget, discipline rules get copied into notes, and then three layers disagree with each other and all look authoritative.

## Quick start

```bash
git clone <this repo>
cd agent-memory-kit

# 1. What can this machine actually do?
python3 scripts/probe.py --out env.probe.json

# 2. Generate the layers, adapted to what was detected
python3 scripts/scaffold.py --target ~/memory-vault --name "Your Name" --probe env.probe.json

# 3. Fill in L1 and L2, then audit everything
python3 scripts/check_all.py --config ./memory.config.json --vault ~/memory-vault
```

No dependencies. Python 3.8+. macOS, Linux, Windows.

Nothing is overwritten without `--force`. `--dry-run` prints the plan and writes nothing.

## Supported agents

`probe.py` detects what is installed and `scaffold.py` writes the file that agent actually reads:

| Agent | Rule file | Lifecycle hooks | MCP | Notes |
|---|---|---|---|---|
| Claude Code | `CLAUDE.md` | yes | yes | best case: real auto-recall |
| Codex CLI | `AGENTS.md` | no | yes | manual recall |
| WorkBuddy / CodeBuddy | `MEMORY.md` | no | yes | MCP is tool-call style |
| DSH (DeepSeek Harness) | `AGENTS.md` | yes | yes | lifecycle plugin |
| Pi (pi.dev) | `AGENTS.md` | yes, if you write one | yes (`mcp.json`) | also loads `CLAUDE.md` — budgets add up |
| Cursor | `.cursor/rules/memory.mdc` | no | yes | manual recall |
| Gemini CLI | `GEMINI.md` | no | yes | manual recall |
| Anything else | `AGENTS.md` | no | maybe | degrade to pasted memory card |

Adding a platform means adding one row to `PLATFORMS` in `scripts/probe.py`. Nothing else changes.

## The four checks

This is the part you cannot get from a memory SDK. Each check maps to a failure that looks like success until you measure it.

| Check | Question | Exit 1 when |
|---|---|---|
| `link_check.py` | Does every `[[wikilink]]` resolve to a real note? | any pointer dangles |
| `budget_check.py` | Does the discipline layer fit the host's injection cap? | over the safe cap |
| `false_green.py` | Does recall separate real queries from garbage? | no safe threshold window |
| `layer_dup.py` | Are the three layers actually different content? | layers duplicate each other |

```bash
python3 scripts/link_check.py  --vault ~/memory-vault
python3 scripts/budget_check.py --config ./memory.config.json
python3 scripts/false_green.py --vault ~/memory-vault
python3 scripts/layer_dup.py   --discipline ./MEMORY.md --vault ~/memory-vault
```

All four return non-zero on failure, so they drop into CI unchanged.

### Why `false_green.py` exists

Counting returned rows is not evidence. Lower the similarity threshold far enough and a string of random characters returns three confident results. The script sweeps thresholds and looks for a **safe operating window**: real queries still hit, garbage and negative controls return nothing. If no such window exists, the retrieval is decoration.

Run it on `examples/demo-vault` to see the output shape.

## Tests

A linter that only ever prints PASS is decoration. `scripts/selftest.py` drives the
pipeline both ways: clean input must pass, each injected defect must fail the
matching check, and the failure must clear once the defect is removed.

```bash
python3 scripts/selftest.py      # 29 assertions, offline, no dependencies
```

| Assertion | Why it is there |
|---|---|
| Dangling link makes the audit exit 1 | otherwise "green" means nothing |
| Over-budget discipline exits 1 | overflow is a failure, not a warning |
| Rules copied into the vault exit 1 | duplication is caught, not tolerated |
| An identity file inside the vault is not self-compared | a real false positive this repo shipped once |
| A one-note vault is refused, not scored | `false_green` must decline to grade what it cannot separate |
| Pi is detected from `~/.pi/agent` and its quirks are reported | platform table rows are claims; this keeps them honest |
| No absolute home paths in tracked files | this repo leaked local paths once already |
| `SKILL.md` carries the fields the marketplace rejects without | the package is refused at upload, weeks after the fact |
| The A/B harness reports a gap for a context-following agent | otherwise the table it writes is decoration |
| The same harness exits 3 when the agent ignores context | a tool that cannot say "no difference" only produces false greens |
| An engine that prints nothing aborts the run | silence was scored as a wrong answer once, which fabricates the gap |
| The A/B table quotes the agent verbatim | a score without the sentence behind it is not evidence |

`.github/workflows/audit.yml` runs that exact command on Linux, macOS and Windows
across Python 3.10–3.13, then audits the example vault, then fails if any script
left a file behind in the working tree.

## Does the discipline layer actually do anything?

Every memory project assumes its context file helps. That is testable, and Pi
hands you the switch: `-nc` / `--no-context-files` loads **no** `AGENTS.md` and
**no** `CLAUDE.md`. Same binary, same model, same question — one condition has
your rules in the prompt, the other has nothing.

`scripts/ab_context.py` runs that comparison. Six questions, all of them
unanswerable from general knowledge because they ask about conventions this
scaffolder invented: what happens when the character budget overflows, which
prefix holds dead work, how many notes you may read before admitting the index is
wrong, where decisions live and whether one may be rewritten.

| Question | With context file | With `-nc` |
|---|---|---|
| What does the host do when the memory-rules budget is exceeded? | **correct** — "the host injects nothing at all — it does not truncate" | not available |
| Where do decisions with reasons get written, and may one be rewritten? | **correct** — "`04-decisions`, append-only, never rewrite history" | not available |
| How many notes may be read before concluding the index is wrong? | **correct** — "at most three notes; if three are not enough, the index is wrong" | not available |
| Which prefix holds finished or dead work? | **correct** — "`10-archive` … moved there rather than deleted" | **"ex-", as in former or no longer active** |
| A note seems to need two titles. What do you do? | **correct** — "split it into two notes, one topic each" | **"use a compound title (e.g. `Main Title: Subtitle`)"** |
| What storage does this memory system use? | **correct** — "plain markdown files … no database, embedding store, or index server" | not available |

`6/6` with the file, `0/6` without it, 3 runs per cell. The raw run, quotes
included, is [`AB-RESULT.md`](AB-RESULT.md) — generated by the command below, not
typed by hand.

Two of the six `-nc` answers are worse than ignorance: asked which prefix holds
dead work, the model invented **`ex-`**; asked what to do with a note needing two
titles, it invented a **compound-title convention**. Those are the failure mode
this file prevents — a confident answer to a question you never wrote down a rule
for. The trap row did *not* fire: without context the model admitted "not
available" rather than inventing a database, so the strongest case in the table
is fabrication of conventions, not fabrication of infrastructure.

**How it was measured** (2026-11-16, one model, one machine — this is a
demonstration, not a benchmark):

```bash
export LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-v4-flash
export LLM_API_KEY=...                       # your key, never committed
python3 scripts/ab_context.py \
  --engine custom --cmd "python3 examples/llm-once.py" \
  --discipline rules/AGENTS.md --extra vault/AGENTS.md --index vault/00-index.md \
  --repeat 3 --markdown AB-RESULT.md
```

`examples/llm-once.py` is a dependency-free stdin→stdout adapter for any
OpenAI-compatible endpoint, so this table is reproducible with your own model
instead of trusted on my word. If your run scores equal, believe your run: your
rubric is too easy, or the file carries nothing the agent needs.

One caveat worth stating because it nearly shipped: the first attempt printed
**empty** answers for five cells, and the harness scored that silence as "wrong"
— a perfect `6/0` produced by a broken engine rather than a load-bearing file.
`run_engine()` now aborts on empty output, and `selftest.py` asserts it. The full
case, including why raising `max_tokens` does not fix it, is anti-pattern
[#10](references/anti-patterns.md).

On Pi you get the switch for free; on any other host `ab_context.py` injects the
files itself, which measures the same thing with one less moving part:

```bash
python3 scripts/ab_context.py --engine pi --model <model> \
  --discipline ~/.pi/agent/AGENTS.md --extra ./AGENTS.md --index ./00-index.md \
  --repeat 3 --markdown AB-RESULT.md

python3 scripts/ab_context.py --discipline ./AGENTS.md --engine ollama --model qwen2.5:7b
```

How to read the output:

| Outcome | What it means | What to do |
|---|---|---|
| `ctx` answers, `-nc` says "not available" | the file is load-bearing | keep it, and keep it under budget |
| Both answer correctly | your questions are answerable from priors — the rubric is too easy | ask about invented conventions, not general practice |
| `-nc` invents a database or a directory that does not exist | the trap row fired | that is the strongest case for the file: it suppresses fabrication |
| Exit code `3` | no gap found, the harness refuses to call it a win | delete the file or rewrite it around facts a model cannot guess |

The harness itself is self-tested, because a measurement tool that cannot report
"no difference" is just a generator of false greens:
`stub-echo` (repeats the injected text) scores 6/6 and exits 0, `stub-silent`
(generic answers) scores 0/6 and exits 3. Both are asserted in
`scripts/selftest.py`, so CI fails if the harness ever stops discriminating.

## Memory backends

The fact layer is plain markdown, so any backend that can read files works.

| Backend | Setup | Cross-agent | Notes |
|---|---|---|---|
| `filesystem` | none | one machine | default, zero cost |
| `git` | one repo | any machine | best for multi-machine |
| `mcp-filesystem` | MCP server | any MCP-capable agent | agents read/write through MCP |
| `memos` | MemOS Cloud account | yes, same `user_id` | semantic layer; see caveat below |

**MCP is not a hook.** An MCP memory server exposes `search_memory` / `add_message`. Nothing enters your context unless something calls those tools. On a host without lifecycle hooks, "shared memory" means *shared when asked*, not *automatic*. See [`references/backends.md`](references/backends.md).

## Capability boundary

Read this before believing any claim about automatic memory.

- **Auto-recall requires a host lifecycle hook.** Claude Code and DSH have them. WorkBuddy, Codex, Cursor, and Gemini CLI do not — on those hosts recall is manual or tool-triggered. `probe.py` reports the truth; `scaffold.py` writes a manual-recall block instead of pretending.
- **On Pi the hook is code you write, not a config block.** Pi has no `hooks` JSON; a TypeScript extension in `~/.pi/agent/extensions/` can inject context before each turn. Capable and honest, but it will not exist until you build it.
- **The identity layer is host-provided.** If your agent has no cloud memory, L1 collapses into the top of L2 and you lose the "follows the account" property.
- **Cross-agent sharing needs a third place.** A folder, a git remote, or a service. Two agents do not share memory by both having a memory feature.
- **This tool does not write your notes.** It generates structure and audits it. The value is in the notes you actually fill in.

## Install as a skill

`SKILL.md` is written so an agent can drive the whole flow itself. Copy the repo into your skills directory:

```bash
# Claude Code
cp -r agent-memory-kit ~/.claude/skills/

# WorkBuddy / CodeBuddy
cp -r agent-memory-kit ~/.workbuddy/skills/
```

Then ask your agent: *"set up my memory system"* and it will probe, scaffold, and audit.

## What this is not

- Not a vector database, an embedding service, or an MCP server
- Not a note-taking app
- Not a promise that your agent will remember automatically
- Not a place to store secrets — the discipline file is injected into every session

## Publishing to the skill marketplace

The upload package is not this repository. The repository carries a demo vault
nested four levels deep and a CI workflow; the marketplace accepts one top-level
folder with at most one level of subfolder inside it, under 3 MB, with five
extra frontmatter fields. `scripts/package_skill.py` stages an allowlist, checks
all of that, runs the packaged copy's own tests, and only then writes the zip:

```bash
python3 scripts/package_skill.py           # dist/agent-memory-kit.zip, 58 KB
python3 scripts/package_skill.py --check   # rules only, no archive (CI runs this)
```

Listing copy and the release checklist are in [`MARKETPLACE.md`](MARKETPLACE.md).

## More

- [`references/platform-matrix.md`](references/platform-matrix.md) — exact paths and capabilities per agent
- [`references/backends.md`](references/backends.md) — filesystem / git / MCP / MemOS in detail
- [`references/anti-patterns.md`](references/anti-patterns.md) — ten ways these systems fail

## License

MIT
