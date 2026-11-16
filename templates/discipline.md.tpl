# Memory Rules — discipline layer

> Budget: **{{BUDGET}} characters**. If this file exceeds the budget the host
> injects **nothing at all** — it does not truncate. Count before you add.
> Vault: `{{VAULT}}` · Platform: `{{PLATFORM}}` · Recall mode: `{{AUTO_MODE}}`

## Who I work for

<!-- Fill these three lines, then delete this comment. Keep it short. -->

- Name: {{NAME}}
- Language / tone:
- Output shape: (conclusions first? tables? numbered lists?)
- Hard red lines: (what must never happen, in any task)

## How to use memory

1. Before a non-trivial task, grep `{{INDEX}}` for the topic. Do not read the
   whole vault.
2. Read at most three notes. If three are not enough, the index is wrong — fix
   the index instead of reading more.
3. If recall returns nothing, say "no prior context" and proceed. Do not invent
   history to look helpful.

{{RECALL_SECTION}}

## Writing back

Write a note back only when one of these is true:

- a durable preference appeared
- a decision was made and a reason was given
- a fact contradicts something already in the vault
- a procedure will be repeated

Do not write back tool errors, transient states, or restatements of the current
conversation. A bloated vault is the same failure as an empty one.

## Pointers

Everything here is a pointer, not a copy. Details live in the vault.

- how I work → `{{VAULT}}/00-index.md` → `about-me`
- standing rules → `working-agreements`

After any edit run `python3 scripts/link_check.py --vault {{VAULT}}`.
A dangling pointer is worse than no pointer: it teaches the agent that this file
lies, and then it stops trusting every rule in it.

## Budget discipline

This file holds cross-project hard constraints only. Project detail belongs in
the vault. When over budget: merge duplicates, drop anything a tool already
enforces, move examples into a note and leave the pointer behind. Never cut a
rule in half to make room.

## Boundaries

- No secrets, keys, or credentials in this file.
- Do not describe this setup as fully automatic unless a hook is actually
  running. Current mode: **{{AUTO_MODE}}**.
- MCP: **{{MCP_STATUS}}**. MCP is tool-call style, not a hook. Nothing reaches
  your context unless something calls it.
