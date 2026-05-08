<!-- repo-task-proof-loop:start -->
## Repo task proof loop

For substantial features, refactors, and bug fixes, use the repo-task-proof-loop workflow.

Required artifact path:
- Keep all task artifacts in `.agent/tasks/<TASK_ID>/` inside this repository.

Required sequence:
1. Initialize `.agent/tasks/<TASK_ID>/` and keep all durable workflow state there.
2. Route the task and write `.agent/tasks/<TASK_ID>/routing.json` plus any child briefs under `.agent/tasks/<TASK_ID>/dispatches/`.
3. Freeze `.agent/tasks/<TASK_ID>/spec.md` before write-capable implementation work.
4. Route again from the frozen spec before implementation fan-out.
5. Implement against explicit acceptance criteria (`AC1`, `AC2`, ...).
6. Create `evidence.md`, `evidence.json`, and raw artifacts.
7. Run a fresh verification pass against the current codebase and rerun checks.
8. If verification is not `PASS`, write `problems.md`, apply the smallest safe fix, and reverify.

Hard rules:
- Do not claim completion unless every acceptance criterion is `PASS`.
- Treat skill invocation as authorization for bounded child orchestration inside this workflow, but prefer the smallest valid decomposition and stay serial when delegation is unnecessary.
- Verifiers judge current code and current command results, not prior chat claims.
- Fixers should make the smallest defensible diff.
- Route from repo-local artifacts, not from assuming a full raw parent transcript handoff. Child briefs in `dispatches/` are the scoped contract beyond the frozen spec.
- Before spec freeze, only `task-scout` or `task-explorer` may be scheduled.
- After spec freeze, prefer `.codex/agents/task-router.toml` to choose the smallest valid child setup, keep the task tree shallow, keep evidence ownership with one builder, and keep verdict ownership with one fresh verifier. Use built-in generic helpers only as fallback when the task-specific roles are unavailable in the current product surface.
- Keep `.codex/agents/task-builder.toml` inheritance-first so the parent session controls implementation depth.
- Prefer `.codex/agents/task-router.toml` for route decisions, dispatch briefs, and minimal bounded decomposition.
- Prefer `.codex/agents/task-scout.toml` for the cheapest read-only lookup work: ownership, path mapping, symbol location, test or config discovery, and narrow proof probes.
- Prefer `.codex/agents/task-explorer.toml` for deeper read-only tracing: execution flow, contracts, invariants, cross-file causality, and evidence-gap analysis.
- Prefer `.codex/agents/task-worker-lite.toml` for one-file or tightly bounded low-risk edits with explicit ownership.
- Prefer `.codex/agents/task-worker-strong.toml` for bounded multi-file or ambiguity-prone edits after the scope is understood.
- This root `AGENTS.md` block is the repo-wide Codex baseline. More-specific nested `AGENTS.override.md` or `AGENTS.md` files still take precedence for their directory trees.
- Keep this block lean. If the workflow needs more Codex guidance, prefer nested `AGENTS.md` / `AGENTS.override.md` files or configured fallback guide docs instead of expanding this root block indefinitely.

Installed workflow agents:
- `.codex/agents/task-router.toml`
- `.codex/agents/task-spec-freezer.toml`
- `.codex/agents/task-scout.toml`
- `.codex/agents/task-explorer.toml`
- `.codex/agents/task-builder.toml`
- `.codex/agents/task-worker-lite.toml`
- `.codex/agents/task-worker-strong.toml`
- `.codex/agents/task-verifier.toml`
- `.codex/agents/task-fixer.toml`
<!-- repo-task-proof-loop:end -->
