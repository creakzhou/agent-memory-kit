# Platform matrix

What each agent actually reads, and what it can actually do. Everything here is
detected by `scripts/probe.py` at runtime — this file explains the results, it is
not a substitute for running the probe.

## Capability matrix

| Agent | Rule file (project) | Global / profile memory | Auto-inject rule file | Lifecycle hooks | MCP | Skills |
|---|---|---|---|---|---|---|
| Claude Code | `CLAUDE.md` | `~/.claude/CLAUDE.md` | yes | **yes** (`settings.json` → `hooks`) | yes | `~/.claude/skills` |
| Codex CLI | `AGENTS.md` | `~/.codex/AGENTS.md` | yes | no | yes (`config.toml`) | no |
| WorkBuddy / CodeBuddy | `AGENTS.md` | `~/.workbuddy/memory/MEMORY.md` | partial | **no** | yes (`~/.workbuddy/mcp.json`) | `~/.workbuddy/skills` |
| DSH (DeepSeek Harness) | `AGENTS.md` | plugin-managed | via plugin | **yes** (plugin) | yes | plugin |
| Pi (pi.dev) | `AGENTS.md` **+** `CLAUDE.md` | `~/.pi/agent/AGENTS.md` | yes | **yes** (TypeScript extension) | yes (`mcp.json`) | `~/.pi/agent/skills` |
| Cursor | `.cursor/rules/*.mdc` | `~/.cursor/rules` | yes | no | yes | no |
| Gemini CLI | `GEMINI.md` | `~/.gemini/GEMINI.md` | yes | no | yes | no |
| Anything else | `AGENTS.md` | — | manual | no | maybe | no |

`auto-inject` means the host puts the file into context without being asked.
That property, not the file name, is what makes a layer automatic.

## Per-platform notes

### Claude Code

- Project rule file is `CLAUDE.md`, loaded from the working directory upward.
- Real hook support: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
  `Stop`. This is the only widely-used host where automatic recall is honest.
- MCP servers live in `~/.claude.json` or a project `.mcp.json`.
- Skills in `~/.claude/skills/<name>/SKILL.md`.

Minimal recall hook shape. This repo does **not** ship a recall script — the
snippet shows where one plugs in. Writing it means: read the prompt, grep the
vault index, print the top few notes to stdout.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 /path/to/your-recall-script.py" } ] }
    ]
  }
}
```

Schemas change between releases. Check the current hook docs before relying on it.

### Codex CLI

- `AGENTS.md` is read automatically; there is no hook system.
- MCP servers are declared in `~/.codex/config.toml` as `[mcp_servers.<name>]`.
- Recall is manual. The discipline file must contain explicit triggers.

### WorkBuddy / CodeBuddy

- `AGENTS.md` in the project plus a user-level `MEMORY.md` under
  `~/.workbuddy/memory/`.
- **No symmetric lifecycle hook.** MCP is tool-call style: the server is reachable
  and the tools work, but nothing is injected unless a tool is called.
- The `MUST be auto-invoked by the client` phrasing found in some MCP server
  descriptions is addressed to the model, not enforced by the host. Do not read it
  as "the client will inject this for me".

### DSH (DeepSeek Harness)

- Uses a lifecycle plugin rather than a static rule file: recall runs before the
  prompt is built, write-back runs at agent end.
- This is the most thorough model of the four, because recall cannot be skipped by
  the model forgetting to ask.
- Probe looks for `~/.dsh` / `~/.deepseek-harness` and reports whether a plugin is
  configured.

### Pi (pi.dev)

- Reads **`AGENTS.md` and `CLAUDE.md`**, each from `~/.pi/agent/`, every parent
  directory, and the cwd. Both load when both exist. This is the one host where
  "just add an `AGENTS.md`" silently doubles the injected budget; `probe.py`
  prints it on the agent row and `scaffold.py` warns when it finds the sibling.
- `SYSTEM.md` (`~/.pi/agent/` global, `.pi/` project) **replaces** the default
  system prompt; `APPEND_SYSTEM.md` appends to it. This is the loudest lever you
  have — and the fastest way to wreck the agent if you paste 4k chars of rules in.
- **No JSON hook block.** Extensions are TypeScript modules in
  `~/.pi/agent/extensions/` (global) or `.pi/extensions/` (project). They can
  inject messages before each turn, filter history, and implement long-term
  memory, but they run with your permissions and none ship by default. So
  auto-recall is possible, not free — same rule as everywhere else: it is
  automatic only once you have written the extension.
- MCP is built in (since 1.0): `~/.pi/agent/mcp.json` for user servers,
  `.pi/mcp.json` for project servers, which load only after project trust. Same
  `mcpServers` shape as Claude Code. Tools reach the model through `codemode` by
  default rather than being listed in the prompt.
- Skills in `~/.pi/agent/skills/` and `.pi/skills/`; prompt templates in
  `prompts/`; bundles via `pi install npm:...` or `git:...`.
- `/reload` picks up edited context files without restarting. `--no-context-files`
  (`-nc`) disables loading entirely — the cheapest honest A/B test of whether
  your discipline file is doing anything at all.
- Budget: the default system prompt is under ~1k tokens, so 3.6k chars of
  discipline is proportionally far louder here than on Claude Code. The
  scaffolder uses 3600 for that reason.

### Cursor

- Rules live in `.cursor/rules/*.mdc` (or the legacy `.cursorrules`).
- No hooks. MCP is supported but tool-call style.
- Budget is smaller than the CLI agents; the scaffolder uses 3,000 chars here.

### Gemini CLI

- `GEMINI.md`, no hooks, MCP supported.
- Same manual-recall pattern as Codex.

### Adding a platform

One row in `PLATFORMS` inside `scripts/probe.py`:

```python
{
    "id": "my-agent",
    "label": "My Agent",
    "detect_dirs": [HOME / ".myagent"],
    "detect_env": ["MYAGENT_HOME"],
    "rule_file": "MYAGENT.md",
    "global_rule": HOME / ".myagent" / "MYAGENT.md",
    "hooks": {"supported": False, "config": None, "note": "none"},
    "mcp_configs": [HOME / ".myagent" / "mcp.json"],
    "skills_dir": None,
},
```

Then add the rule filename to `PLATFORM_RULES` in `scripts/scaffold.py`. No other
file needs to change — the checks operate on content, not on platform.
