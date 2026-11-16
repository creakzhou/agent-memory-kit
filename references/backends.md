# Memory backends

The fact layer is plain markdown in a folder. Pick a backend by asking one
question: **how many machines and how many agents need to read it?**

| Need | Backend | Cost |
|---|---|---|
| One machine, one agent | `filesystem` | none |
| One machine, two agents | `filesystem` + shared path | none |
| Two machines | `git` | none |
| Several agents, no shared disk | `mcp-filesystem` | an MCP server |
| Cross-language recall, semantic search | `memos` | a service account |

## filesystem (default)

The vault is a directory. Agents read it with file tools or shell commands.

- **Works everywhere.** Every agent in the matrix can read files.
- **No sync problem**, because there is only one copy.
- **Fails at:** two machines, and agents that cannot run commands (chat-only UIs).

`scaffold.py` sets this by default and writes `backend.kind = "filesystem"`.

## git

Same folder, plus a remote. Each machine clones it.

- **Best multi-machine option.** History, conflict detection, and a free backup.
- **Do not pull-rebase blindly.** The vault is usually edited by an agent that will
  happily overwrite notes. Commit before pulling.
- **Never put the discipline file in the same repo as the vault** if the discipline
  file is machine-specific — you will fight conflicts on every sync.

## mcp-filesystem

Agents read and write the vault through an MCP filesystem server instead of raw
shell access. Useful when the agent is sandboxed and cannot touch arbitrary paths.

- The server is a **port**, not a memory. It grants path access; it does not inject
  anything into context.
- Point it at the vault directory only, never at the home directory.

## memos (MemOS Cloud)

A semantic layer that both agents can use with the same `user_id`.

How it actually behaves:

| Property | Reality |
|---|---|
| Transport | MCP tools: `search_memory`, `add_message` (names vary by version) |
| Isolation | by `user_id`; same id = shared memory, no sync script needed |
| Injection | **none** unless a tool is called |
| Versioning | none; it is a semantic layer, not a source of truth |
| Conflict handling | none; two agents can write contradictory facts |

Rules that keep it honest:

1. **The vault is the source of truth. MemOS is a hint layer.** If a recalled
   memory contradicts a note in the vault, the vault wins, and you say the two
   disagree instead of quietly picking one.
2. **`user_id` is not a secret, but it is identity.** Never commit it to a public
   repo. Load it from an environment variable.
3. **Thresholds are the trap.** A low similarity threshold makes every query return
   something, including garbage. Calibrate with a negative control, not with hit
   count — see `scripts/false_green.py`.
4. **Write back selectively.** A memory layer that stores everything becomes a
   transcript dump and starts returning old noise as context.

## Mixed setups

The realistic answer is a mix:

```
L1 identity   -> host cloud memory (if any)
L2 discipline -> local rule file, machine-specific, not in git
L3 facts      -> git-backed markdown vault
                + memos for cross-agent semantic recall
```

Keep the fact layer authoritative and everything else a cache. When a cache disagrees
with the vault, the vault is right.
