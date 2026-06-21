# Harness portability — running this project's skills + commands outside Claude Code

The TikiTakaFootyTV brain (skills) and pipeline drivers (slash commands) are authored
for **Claude Code**, but they're plain markdown + prose, so they port to other coding
harnesses with very little glue. **OpenCode** is the first supported target.

`.claude/` is the **single source of truth.** Don't hand-edit the generated copies —
edit the originals under `.claude/`, then run the sync.

```bash
python3 pipeline/sync_harness.py sync     # regenerate every harness copy
python3 pipeline/sync_harness.py check    # report drift (exit 1 if stale) — write nothing
```

## What ports, and how

| Artifact | Claude Code | OpenCode | Action by `sync_harness.py` |
|---|---|---|---|
| **Skills** (`.claude/skills/<name>/SKILL.md`) | read from `.claude/skills/` | **read from `.claude/skills/` natively** (same `name`+`description` format; also reads `.agents/skills/`) | none — already portable; sync only sanity-checks them |
| **Commands** (`.claude/commands/<name>.md`) | read from `.claude/commands/` | read from `.opencode/command/` (singular), different frontmatter | translates → `.opencode/command/<name>.md` |
| **Project instructions** | `CLAUDE.md` | `AGENTS.md` | bridges `AGENTS.md` → `CLAUDE.md` (symlink; stub fallback) |

### Skills — already work in OpenCode, no copy

OpenCode discovers `SKILL.md` files from (in order) `.opencode/skills/`,
`~/.config/opencode/skills/`, **`.claude/skills/`**, and **`.agents/skills/`**. Our 6
skills live in `.claude/skills/` and the `find-skills` skill is symlinked from
`.agents/skills/` — both paths OpenCode reads. So every skill is available in OpenCode
unchanged. The sync step only validates that each skill's `name` matches its directory
(OpenCode keys on that) and that `description` is present.

### Commands — translated to OpenCode's dialect

OpenCode command frontmatter differs from Claude Code's:

- **dropped** `allowed-tools` — OpenCode scopes tools per *agent*, not per command.
- **dropped** `argument-hint` — no such field in OpenCode.
- **`model`** is rewritten to OpenCode's `provider/model` form (e.g. `claude-haiku-4-5`
  → `anthropic/claude-haiku-4-5`). If you run OpenCode against a different backend,
  repoint the provider prefix in `MODEL_MAP` in `pipeline/sync_harness.py`.
- the **body is copied verbatim**: `$ARGUMENTS`, `$1`, `` !`shell` ``, and `@file` all
  work in both, and the commands invoke skills in prose ("invoke the `videospec` skill"),
  which both harnesses understand.

Each generated file carries an `AUTO-GENERATED … do not edit by hand` banner.

## Using it in OpenCode

1. `python3 pipeline/sync_harness.py sync` (already run; re-run after editing any
   `.claude/commands/*.md` or adding a skill).
2. Open the repo in OpenCode. Skills auto-discover; commands appear as `/daily`,
   `/find-topics`, `/publish`, `/storyboard`, `/analyze-channel`, `/reply-comments`.
3. OpenCode loads project context from `AGENTS.md` (→ `CLAUDE.md`).

> The deterministic pipeline (`uv run pipeline/…`, `make_video.sh`, Remotion, ElevenLabs)
> is harness-agnostic — it's just shell/Python the command bodies call, identical everywhere.

## Adding another harness

`sync_harness.py` is structured around per-target generators. To support a new harness,
add a generator alongside `sync_opencode_commands()` that emits its command/skill format
and instruction-file bridge, then call it from `main()`. Keep `.claude/` the source of
truth so there's one place to edit.
