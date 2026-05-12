---
name: repo-task-proof-loop
description: Repo-local proof-loop skill for large coding tasks. Initializes durable task artifacts, routes from repo-local task state, installs Codex subagents by default, optionally installs Claude compatibility files when explicitly requested, updates repo guidance, and runs a route → freeze → route → build → evidence → verify → fix loop with fresh-session verification.
license: Apache-2.0
compatibility: Skills-compatible coding agents. Maintained for Codex-first project-scoped subagents, with optional Claude compatibility surfaces when explicitly requested. Bundled scripts require Python 3.10+.
metadata:
  author: OpenAI
  version: "1.0.0"
---

# Repo Task Proof Loop

This installed copy is a Codex-focused fork of [DenisSergeevitch/repo-task-proof-loop](https://github.com/DenisSergeevitch/repo-task-proof-loop). It keeps the same proof-loop core, but changes the Codex path to be Codex-first, Windows-safe, and cost-aware through explicit helper roles.

Use this skill when the user wants a repeatable, auditable implementation workflow for a non-trivial coding task, especially a feature, refactor, migration, or bug fix that should leave repo-local proof in `.agent/tasks/<TASK_ID>/`.

All task artifacts created by this workflow must stay inside the repository.

When the examples below mention `scripts/task_loop.py`, that path is relative to this skill root. Run it while your shell working directory is inside the target repository.

## What this skill does

1. Initializes a strict repo-local task folder under `.agent/tasks/<TASK_ID>/`
2. Seeds or updates the required artifact files
3. Installs project-scoped Codex subagent templates by default into `.codex/agents/` and, only when explicitly requested, Claude compatibility files into `.claude/agents/`
4. Writes and refreshes durable routing state in `.agent/tasks/<TASK_ID>/routing.json` plus scoped child briefs under `.agent/tasks/<TASK_ID>/dispatches/`
5. Updates the matching repo guide files with a managed block that explains the workflow
6. Guides the agent through a strict loop:
   - route
   - spec freeze
   - route
   - builder implementation
   - evidence packing
   - fresh verification
   - minimal fix
   - fresh verification again until `PASS`

See:
- `references/REFERENCE.md`
- `references/COMMANDS.md`
- `references/SUBAGENTS.md`
- `references/SCHEMAS.md`

## Commands this skill supports

Treat the following words as commands when the user invokes this skill:

- `init <TASK_ID>`: create `.agent/tasks/<TASK_ID>/`, install or refresh the selected subagent templates, and update the matching guide files
- `route <TASK_ID>`: read the current task artifacts, write `routing.json`, and emit scoped dispatch briefs for the next task phase
- `freeze <TASK_ID>`: create or refine `spec.md` from the user task, task file, and repo guidance
- `build <TASK_ID>`: implement the task against the frozen spec
- `evidence <TASK_ID>`: create or refresh `evidence.md`, `evidence.json`, and raw artifacts without changing production code
- `verify <TASK_ID>`: run a fresh verifier pass and write `verdict.json`, plus `problems.md` when needed
- `fix <TASK_ID>`: apply the smallest safe fix set from `problems.md`, then refresh the evidence bundle
- `run <TASK_ID>`: execute the full loop from spec freeze through verification
- `status <TASK_ID>`: summarize current artifact status

If the user does not supply a command, infer the next step from repo state:
- If the task folder does not exist, run `init` first. If the user clearly wants initialization only, stop there. Otherwise, after `init` succeeds, continue by re-evaluating repo state in the same turn. Do not overlap `init` with `route`, `freeze`, `build`, `evidence`, `verify`, `fix`, `validate`, `status`, or subagent work.
- If `routing.json` is missing, unrouted, or stale for the current phase, do `route`
- If `spec.md` is missing or placeholder-only, do `freeze`
- If `spec.md` just became frozen, do `route` again before write-capable implementation work
- If implementation is not yet complete, do `build`
- If evidence is stale or missing, do `evidence`
- If no fresh verdict exists, do `verify`
- If verdict is not `PASS`, do `fix`

## Initialization step

Run the bundled initializer from the repository root or current working directory inside the repo:

```bash
scripts/task_loop.py init --task-id <TASK_ID>
```

Optional task seeding:

```bash
scripts/task_loop.py init --task-id <TASK_ID> --task-file path/to/task.md
scripts/task_loop.py init --task-id <TASK_ID> --task-text "User task text"
```

The initializer will:

- resolve the repo root
- create `.agent/tasks/<TASK_ID>/`
- create all required artifacts, including placeholders under `raw/`
- install project-scoped subagent files for the selected profile
- insert or refresh managed workflow blocks in the selected guide files

For Codex, the initializer keeps its managed workflow block in the repo-root `AGENTS.md`. Codex also supports `AGENTS.override.md` and configured fallback guide filenames; nested files closer to the code still take precedence, and this skill intentionally does not overwrite them.
If `init` creates or rewrites `AGENTS.md` during a running Codex session, start a new Codex session before relying on the updated instructions. Codex snapshots project-doc guidance at session start.

If you explicitly enable Claude compatibility, the initializer keeps its managed workflow block in the repo-root `CLAUDE.md`. Claude Code also supports `.claude/CLAUDE.md`, `.claude/rules/*.md`, and `CLAUDE.local.md`, but that path is compatibility-only in this fork rather than the primary documented workflow.

In Claude Code, if `init` just wrote or refreshed `.claude/agents/*` during the current session, do not assume those updated agents are already available mid-session.

Treat `init` as a serial prerequisite. Never overlap it with `route`, `freeze`, `build`, `evidence`, `verify`, `fix`, `validate`, `status`, or child-agent spawning.

## Routing step

Run the durable router after `init` and again after the spec is frozen:

```bash
scripts/task_loop.py route --task-id <TASK_ID>
```

Routing rules:

- Before the spec is frozen, routing may only choose `serial`, `task-scout`, or `task-explorer`.
- After the spec is frozen, routing may emit `task-builder`, `task-worker-lite`, or `task-worker-strong` dispatches scoped to explicit ACs.
- Child work should follow `routing.json` plus the matching dispatch brief instead of assuming a full raw parent chat handoff.
- Prefer the smallest valid decomposition, state assumptions explicitly, and avoid speculative parallelism.

## Heavy-task default workflow

For large tasks, keep the user-facing request simple. In Codex, the skill should route first and then choose the smallest valid child setup automatically from repo-local task state.

### Preferred delegated sequence

1. Run `init <TASK_ID>` if needed. Wait for it to finish, then confirm `.agent/tasks/<TASK_ID>/spec.md`, `routing.json`, and the repo-local task structure exist before continuing.
2. Run `route <TASK_ID>` and use the route result to decide whether read-only discovery children are necessary before spec freeze.
3. Spawn exactly one spec-freezer subagent and wait for it.
4. Run `route <TASK_ID>` again from the frozen spec.
5. Spawn exactly one builder subagent as the integration owner, plus any bounded worker shards that the route result explicitly scheduled.
6. Continue with the same builder session for evidence packing.
7. Spawn exactly one fresh verifier subagent and wait for it.
8. If verdict is not `PASS`, spawn exactly one fixer subagent, refresh evidence, and verify again.

### Codex adaptive fan-out

Use this when the route result explicitly chooses bounded fan-out. Use the simpler serial sequence above when routing says `serial`.

Good fits:

- multiple independent codebase questions must be answered before the spec is stable
- implementation can be split into disjoint write scopes
- proof requires several independent read-only checks across different surfaces

Codex pattern:

1. `init` stays serial.
2. Before spec freeze, use `routing.json` to decide whether to fan out up to 3 `task-scout` or `task-explorer` children in parallel. Give each one a single question, subsystem, or path scope from its dispatch brief. Use built-in `explorer` only as fallback when the task-specific helper roles are unavailable in the current product surface. Wait for them, then freeze the spec.
3. Spawn one spec-freezer child and wait for it.
4. Route again from the frozen spec.
5. Spawn one `task-builder` child as the integration owner.
5. If implementation splits cleanly, the parent may also spawn bounded helper children in parallel. Prefer `task-scout` for cheap lookup work, `task-explorer` for deeper read-only tracing, `task-worker-lite` for one-file or tightly bounded low-risk edits, and `task-worker-strong` for bounded multi-file or ambiguity-prone edits. Use built-in `worker` only as fallback when the task-specific write-capable helper roles are unavailable in the current product surface. Each worker-style helper must have explicit file or module ownership and must not write `evidence.md`, `evidence.json`, `verdict.json`, or `problems.md`.
6. Use `send_input` or the equivalent follow-up surface to keep the integration builder alive for evidence packing. The builder remains the single owner of the evidence bundle.
7. If extra proof is needed, the parent may fan out a small bounded set of read-only helpers to rerun disjoint checks or inspect separate proof gaps in parallel. Prefer `task-scout` when the question is just “where” or “which file,” and `task-explorer` when the question is “why” or “what real execution path or contract is involved.” Those children may report commands, outputs, and findings, but they do not write `verdict.json`.
8. Run exactly one fresh verifier child for each verify pass.

### Platform behavior

- In Codex, treat skill invocation as authorization for bounded child orchestration inside this workflow, but stay serial when routing says delegation is unnecessary.
- In Codex, the user should not need to name specific child roles or slash commands. The route result should choose the smallest valid child setup automatically.
- In Codex, child spawning is still an explicit parent-orchestrator action. If the current Codex surface blocks delegation, say so briefly only when it materially affects the work, then continue serially.
- In Codex, keep the task tree shallow. The parent session should spawn research, builder, fixer, and verifier children directly instead of asking one custom task child to orchestrate more children.
- In Codex, choose between one-child-at-a-time delegation and bounded fan-out from the current `routing.json`, frozen spec, repo shape, and current delegation surface. Keep `init`, evidence ownership, and every verifier pass serialized either way.
- In Codex, keep helper fan-out modest and wave-based. Prefer up to 3 parallel helper children at once, wait for that wave to finish, then decide the next phase.
- In Codex, the installed task-specific helper roles are the default delegated path. Built-in `explorer` and `worker` are fallback only when the task-specific roles are unavailable in the current product surface.
- In Codex, reuse the live builder child for evidence packing by sending it a follow-up instruction. Verifier passes must use a fresh child or fresh session; do not satisfy verifier freshness by resuming an earlier verifier. Builder and fixer children can be reused or resumed when you intentionally want that context back.
- In Codex, keep `task-builder` inheritance-first so the parent session controls implementation depth.
- In Codex, helper routing should be deliberate and cost-aware. Apply the minimum-sufficient model policy: keep `task-router` and `task-spec-freezer` on `gpt-5.4-mini` for bounded subagent work, use `task-scout` for cheap read-only lookup work, `task-explorer` for deeper read-only tracing, `task-worker-lite` for narrow low-risk edits, and keep stronger code-facing roles such as `task-worker-strong` and `task-verifier` on `gpt-5.3-codex`. Keep inherited parent strength on the integration owner.
- In Codex, inspect the current child-thread list before reusing or resuming a child. Use `/agent` in Codex CLI or any equivalent child-thread inventory surface available in the current Codex product surface.
- In Codex, the plan/todo checklist UI from `update_plan` is optional session guidance only. It is useful for live progress display, but it is not the source of truth for this workflow.
- In Claude Code, the skill should decide whether to stay on the main thread or let the main Claude session auto-delegate the current phase to a matching built-in or project subagent after `init`. The user should not need to request a specific Claude subagent or delegation mode separately.
- In Claude Code, TodoWrite or the visible task/todo UI is optional session-scoped progress display only. It can help with live tracking in the current session, but it is not the source of truth for this workflow.
- In Claude Code, prefer the installed project subagents from `.claude/agents/`, with descriptions written as proactive trigger conditions for the matching proof-loop phase. Claude's main session routes by the task request, subagent descriptions, and current context, so keep each phase prompt clear in natural language. Reuse the same builder child for the evidence step by default. Only run a fresh builder in evidence-only mode if the original builder session is unavailable or you intentionally discarded it. If `init` just refreshed `.claude/agents/*` during the current Claude session, fall back to the main thread or already-visible agents instead of assuming the refreshed ones are available immediately.
- In Claude Code, keep the orchestration flat: main-session auto-delegation is fine, but the proof-loop workflow agents themselves are leaf roles. The parent session should own the proof-loop phase transitions instead of asking one custom task agent to spawn another.
- In Claude Code, the canonical durable state is always the repo-local artifact set under `.agent/tasks/<TASK_ID>/`, especially `spec.md`, `evidence.md`, `evidence.json`, `verdict.json`, and `problems.md`.
- If subagents are unavailable, preserve the same role separation across separate sessions or clear mode changes in the current session.

Use the exact role prompts from `references/COMMANDS.md`.

## Spec freeze requirements

`spec.md` must contain at least:

- original task statement
- explicit acceptance criteria labeled `AC1`, `AC2`, ...
- constraints
- non-goals

It may also include:

- repo guidance sources
- verification plan
- assumptions resolved narrowly from the user request

Do not edit production code during spec freeze.

## Evidence packing requirements

`evidence.md` and `evidence.json` must judge each acceptance criterion independently with one of:

- `PASS`
- `FAIL`
- `UNKNOWN`

Evidence packing may run missing checks, but it must not keep changing production code.

Every `PASS` must cite concrete proof such as:

- file paths
- commands run
- exit codes
- output summaries
- artifact paths under `raw/`

Do not claim overall `PASS` in the evidence bundle unless every acceptance criterion is `PASS`.

## Fresh verification requirements

The verifier must be a fresh session or fresh subagent.
In Codex, do not satisfy this requirement by resuming a prior verifier child.

The verifier must judge the current repository state and current rerun results, not the builder narrative.

The verifier writes:

- `.agent/tasks/<TASK_ID>/verdict.json`
- `.agent/tasks/<TASK_ID>/problems.md` only when overall verdict is not `PASS`

`problems.md` must include, for each non-`PASS` criterion:

- criterion id and text
- status
- why it is not proven
- minimal reproduction steps
- expected vs actual
- affected files
- smallest safe fix
- corrective hint in 1-3 sentences

The verifier must not modify production code or backfill the evidence bundle.

## Fixer requirements

The fixer reads only:

- `spec.md`
- `verdict.json`
- `problems.md`

The fixer must:

- reconfirm each listed problem in the codebase before editing
- make the smallest safe change set
- avoid regressing already-passing criteria
- regenerate `evidence.md`, `evidence.json`, and raw artifacts
- stop without writing final sign-off

## Validation

Before claiming the workflow is correctly initialized or the artifact set is complete, run:

```bash
scripts/task_loop.py validate --task-id <TASK_ID>
```

Run `validate` only after `init` has fully finished. If it reports initialization in progress, wait and rerun it instead of treating that result as stable task failure.

For a quick summary:

```bash
scripts/task_loop.py status --task-id <TASK_ID>
```

Run `status` only after `init` has fully finished when you need stable task state. If it reports `init_in_progress: true`, treat that as a retry-later condition.

## Guardrails

- Keep `.agent/tasks/<TASK_ID>/` inside the repo
- Treat the Codex todo/checklist UI as ephemeral progress only; the durable workflow state lives in `.agent/tasks/<TASK_ID>/`
- Never claim task completion unless every acceptance criterion is `PASS`
- Separate evaluator and fixer roles
- Keep Codex fan-out shallow and bounded. Parallel helpers may inform the proof loop, but one builder still owns evidence and one fresh verifier still owns verdict.
- Keep the verifier fresh
- Prefer the smallest defensible diffs during fixes
- Preserve existing user guidance outside the managed blocks in `AGENTS.md` and the repo's chosen Claude guide file
