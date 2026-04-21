# Fork Summary

This repository is a Codex-focused fork of [DenisSergeevitch/repo-task-proof-loop](https://github.com/DenisSergeevitch/repo-task-proof-loop).

## Why this fork exists

The upstream package is a good proof-loop foundation, but this fork is tuned specifically for Codex-heavy workflows:

- Codex-first default behavior
- token-aware helper routing
- strong parent orchestrator with cheaper bounded helpers
- Windows-safe path handling

## Main fork changes

1. `init` defaults to `--install-subagents codex`.
2. `task-builder` remains inheritance-first, so the parent session controls the main implementation depth.
3. Extra Codex helper roles are installed:
   - `task-scout`
   - `task-explorer`
   - `task-worker-lite`
   - `task-worker-strong`
4. Documentation and managed guide blocks explain when to route work to each helper.
5. Verification was updated so the package smoke-test asserts the helper ladder and Codex-only default path.

## Publishing

If you publish this repository as a standalone GitHub repo, users can install it with the Codex skill installer by pointing it at the repo URL or the repo's root `SKILL.md`.

## Upstream credit

The upstream workflow shape, repo-task artifact model, and original package structure come from DenisSergeevitch's `repo-task-proof-loop`.
