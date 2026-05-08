
# Reference

When the examples below mention `scripts/task_loop.py`, that path is relative to this skill root. Run it while your shell working directory is inside the target repository.

This skill is designed to be portable, but the repository-local artifacts and subagent files it creates must stay in the target repository.
The maintained path in this fork is Codex-first. Claude-related files below describe optional compatibility behavior that is still available in code when explicitly requested.

## Recommended install locations

### Codex

Project skill:
- `.agents/skills/repo-task-proof-loop/`

Personal skill:
- `$HOME/.agents/skills/repo-task-proof-loop/`

### Claude Code compatibility

Project skill:
- `.claude/skills/repo-task-proof-loop/`

Personal skill:
- `~/.claude/skills/repo-task-proof-loop/`

The same skill directory can be reused in either product. The initialization script writes repo-local workflow files into the current repository, not into the skill directory. In this fork, Codex remains the default install and initialization path.

Claude Code note:
- This skill manages its workflow block in the project-root `CLAUDE.md`.
- Claude Code also loads `.claude/CLAUDE.md`, `.claude/rules/*.md`, and `CLAUDE.local.md`, but those remain compatible add-ons outside this skill's managed block.

## Repo files created by `init`

```text
.agent/tasks/TASK_ID/
  spec.md
  routing.json
  dispatches/
  evidence.md
  evidence.json
  raw/
    build.txt
    test-unit.txt
    test-integration.txt
    lint.txt
    screenshot-1.png
  verdict.json
  problems.md
```

The initializer also creates or refreshes these project-level integration files:

```text
.codex/agents/
  task-router.toml
  task-spec-freezer.toml
  task-scout.toml
  task-explorer.toml
  task-builder.toml
  task-worker-lite.toml
  task-worker-strong.toml
  task-verifier.toml
  task-fixer.toml

.claude/agents/
  task-spec-freezer.md
  task-builder.md
  task-verifier.md
  task-fixer.md
```

And it inserts a managed workflow block into:

- repo-root `AGENTS.md`
- optionally, one Claude guide file: `CLAUDE.md` or `.claude/CLAUDE.md`

If both Claude guide locations exist, the initializer updates the repo-root `CLAUDE.md` and leaves `.claude/CLAUDE.md` untouched. The managed block is replaced in place on re-run, so user-authored content outside the managed markers is preserved.
For Codex, the managed block always lives in repo-root `AGENTS.md`. That file acts as the repo-wide baseline. More-specific nested `AGENTS.override.md`, `AGENTS.md`, or configured fallback filenames still take precedence in their directory trees, and the initializer does not rewrite them.
If `init` creates or rewrites `AGENTS.md` during a running Codex session, start a new Codex session before relying on the updated instructions.
In the optional Claude compatibility path, `CLAUDE.md` is the project guide file Claude checks during onboarding. When `--guides auto` is used together with `--install-subagents claude` or `--install-subagents both`, the initializer ensures `CLAUDE.md` exists even if the repo previously only had `AGENTS.md`.

## Commands

### Initialize workflow files

```bash
scripts/task_loop.py init --task-id my-task
```

Codex CLI also has `/init` to scaffold a generic `AGENTS.md`, but this skill's initializer already manages the workflow block and does not require `/init`.

In Claude Code, if `init` just created or refreshed `.claude/agents/*` during the current session, do not assume those refreshed agents are already available mid-session.

Seed the task from a task file:

```bash
scripts/task_loop.py init --task-id my-task --task-file docs/task.md
```

Seed the task from inline text:

```bash
scripts/task_loop.py init --task-id my-task --task-text "Implement feature X"
```

Control which guide files are created or updated:

```bash
scripts/task_loop.py init --task-id my-task --guides auto
scripts/task_loop.py init --task-id my-task --guides both
scripts/task_loop.py init --task-id my-task --guides agents
scripts/task_loop.py init --task-id my-task --guides claude
scripts/task_loop.py init --task-id my-task --guides none
```

For the optional Claude compatibility path, `--guides auto` updates an existing `CLAUDE.md` or `.claude/CLAUDE.md`. If neither exists and Claude subagents are being installed, it creates `CLAUDE.md`.

`--guides auto` keeps existing guide files up to date, creates both guides when none exist yet, and also creates the product-native guide when you install that product's agents (`CLAUDE.md` for the optional Claude path, `AGENTS.md` for Codex).

Control which project subagent sets are installed:

```bash
scripts/task_loop.py init --task-id my-task --install-subagents both
scripts/task_loop.py init --task-id my-task --install-subagents codex
scripts/task_loop.py init --task-id my-task --install-subagents claude
scripts/task_loop.py init --task-id my-task --install-subagents none
```

### Route durable child work

```bash
scripts/task_loop.py route --task-id my-task
```

Run `route` after `init` and again after the spec is frozen. Before spec freeze it may only choose read-only discovery roles. After spec freeze it may emit implementation dispatches scoped to explicit ACs.

### Validate the artifact set

```bash
scripts/task_loop.py validate --task-id my-task
```

Run `validate` only after `init` has finished. If it reports initialization in progress, wait and rerun instead of treating that output as the durable workflow state.

### Summarize current status

```bash
scripts/task_loop.py status --task-id my-task
```

Run `status` only after `init` has finished when you need stable task state. If it returns `init_in_progress: true`, treat that as a retry-later signal.

## Expected working pattern

1. Initialize the task folder
2. Route from repo-local task artifacts
3. Freeze the spec
4. Route again from the frozen spec
5. Implement
6. Pack evidence
7. Fresh verify
8. Fix if needed
9. Fresh verify again

Codex adaptive orchestration:

- Keep normal Codex usage route-first and serial when routing says delegation is unnecessary.
- Treat skill invocation as authorization for bounded child orchestration inside this workflow, but prefer the smallest valid decomposition.
- Once routing chooses bounded fan-out, default to the installed task-specific helper roles for bounded work when a large Codex task has independent research questions, disjoint write scopes, or several read-only proof probes. Use built-in `explorer` or `worker` only as fallback when the task-specific roles are unavailable in the current product surface.
- Keep helper fan-out modest and wave-based. Prefer up to 3 parallel helper children at once, then wait before the next phase.
- Keep the task tree shallow. The parent session should orchestrate children directly instead of asking one custom task child to spawn more children.
- One integration builder still owns `evidence.md` and `evidence.json`.
- One fresh verifier still owns `verdict.json` and `problems.md`.
- Child work should consume `routing.json` plus dispatch briefs instead of assuming a full raw parent transcript handoff.
- Keep `task-builder` inheritance-first so the parent session controls implementation depth.
- Prefer the installed helper roles when you want predictable cost control:
  - `task-router` -> durable route decisions and scoped dispatch briefs
  - `task-scout` -> cheap read-only lookup work
  - `task-explorer` -> deeper read-only tracing
  - `task-worker-lite` -> narrow low-risk edits
  - `task-worker-strong` -> bounded but riskier implementation work
- Keep broad architecture work, integration ownership, and final judgment on the parent, `task-builder`, and `task-verifier`.

For exact prompts to use with child agents, see `references/COMMANDS.md`.

Claude compatibility delegation:

- Let the main Claude Code session decide whether to auto-delegate the current proof-loop phase to a matching project subagent. Users should not need to name a specific Claude subagent for normal operation.
- Keep prompts phase-focused so the current need is obvious, for example “freeze the spec”, “run a fresh verification pass”, or “repair the non-PASS criteria”.
- If automatic delegation is not specific enough, tighten the natural-language prompt for the current proof-loop phase rather than relying on out-of-band controls.
- Keep the proof loop flat even when delegation is automatic. The parent session still owns phase transitions, the evidence bundle stays with one builder, and each verify pass stays fresh.

## Notes

- The initializer does not write the final `spec.md` content for you. It creates the strict file structure and seeds the task statement when provided. The actual spec freeze is an agent step.
- `evidence.json` and `verdict.json` are created with valid placeholder content so validation can run immediately after `init`.
- `raw/screenshot-1.png` is created as a tiny placeholder PNG so the required path exists from the start.
- Guidance discovery for seeded task specs includes repo-visible `AGENTS.override.md`, `AGENTS.md`, root `CLAUDE.md`, `.claude/CLAUDE.md`, and `.claude/rules/**/*.md` when present.
- That seeded guidance list is a workflow artifact, not a literal dump of Codex's automatic project-doc context.
- Codex can also load extra fallback filenames configured via `project_doc_fallback_filenames`. The initializer does not try to infer every user's Codex config layer, so treat the seeded guidance list as best-effort when custom fallback filenames matter.
- Codex may also render an `update_plan` checklist or todo list in the UI. Treat that as ephemeral session progress, not as durable proof-loop state.
- Codex CLI surfaces most relevant to this workflow are `/agent`, `/status`, `/review`, and `/init` (generic scaffold only).
- Before reusing or resuming a Codex child, inspect the current child-thread list in `/agent` in the CLI or the equivalent child-thread inventory surface exposed by the current Codex product surface.
- `task-scout` and `task-explorer` are the preferred Codex roles for read-only repo discovery and proof probes. `task-worker-lite` and `task-worker-strong` are the preferred bounded implementation roles when explicit ownership is possible. Built-in `explorer` / `worker` remain fallback options only when the task-specific roles are unavailable in the current product surface.
- Claude Code also loads `.claude/rules/*.md` and `.claude/CLAUDE.md` as project guidance. The initializer discovers those files when seeding guidance sources for the task.
- After installing or refreshing `.claude/agents/` in the current Claude Code session, do not assume the new agent list is already available.
- Claude Code uses the subagent `description` field to decide when the main session should delegate automatically. Phrase project agent descriptions as proactive trigger conditions when you want Claude to pick them on its own.
- For this workflow, treat the generated Claude agents as flat role endpoints. Do not expect one workflow agent to recursively spawn another.
- Claude Code may also render TodoWrite or a task/todo UI for multi-step work. Treat that as optional session-scoped progress display only. The canonical durable workflow state is the repo-local artifact set under `.agent/tasks/<TASK_ID>/`.
