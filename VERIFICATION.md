# Verification

This package was smoke-tested before packaging.

## Command run

```bash
python scripts/verify_package.py
```

## What the smoke test checks

- `SKILL.md` frontmatter exists and the `name` matches the parent directory
- the skill body is non-empty
- `scripts/task_loop.py init --task-id demo-task --task-text "Implement a demo task."` succeeds inside a fresh temporary git repository
- `scripts/task_loop.py validate --task-id demo-task` returns `valid: true`
- a task-local init sentinel makes `validate` report initialization-in-progress instead of only a misleading missing-files failure when `init` is still active
- `scripts/task_loop.py status --task-id demo-task` reports `init_in_progress: true` when the init sentinel is present
- the expected repo-local artifacts are created under `.agent/tasks/demo-task/`
- project-scoped subagent files are created under `.codex/agents/` and `.claude/agents/`
- `AGENTS.md` and `CLAUDE.md` are created with managed workflow blocks
- generated Codex agent files stay Codex-specific and do not tell Codex to read `CLAUDE.md`
- generated Codex AGENTS guidance mentions the bounded task-specific helper-role fan-out path and keeps built-in generic helpers as fallback only
- generated Codex AGENTS guidance allows `task-scout` / `task-explorer` read-only fan-out before or after spec freeze and keeps `task-worker-lite` / `task-worker-strong` post-freeze only
- generated Codex task-builder template still defines a single integration owner for evidence
- the Codex-facing skill metadata prompt mentions the task-specific helper-role adaptive fan-out path and keeps built-in generic helpers as fallback only
- `references/COMMANDS.md` documents the Codex adaptive fan-out orchestration path, makes the task-specific helper roles the default delegated path, and mentions public child-thread inspection surfaces
- seeded guidance discovery includes `AGENTS.override.md` before `AGENTS.md`
- seeded guidance discovery includes nested `.claude/rules/**/*.md` files
- `--guides auto --install-subagents claude` creates `CLAUDE.md` even if the repo previously only had `AGENTS.md`
- `--guides auto --install-subagents codex` creates `AGENTS.md` even if the repo previously only had `CLAUDE.md`

## Last local result

PASS
