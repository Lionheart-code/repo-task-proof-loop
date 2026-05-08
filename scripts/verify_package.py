#!/usr/bin/env python3
"""Smoke-test the repo-task-proof-loop skill package."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


REQUIRED_FRONTMATTER_KEYS = {"name", "description"}


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError("SKILL.md must start with YAML frontmatter.")
    frontmatter_text, body = match.groups()
    data: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in frontmatter_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z0-9_-]+:", line):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"')
            current_key = key.strip()
        elif current_key and line.startswith("  "):
            continue
    return data, body


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def run_no_check(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=False, text=True, capture_output=True)


def route_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    skill_root = Path(__file__).resolve().parent.parent
    skill_md = skill_root / "SKILL.md"
    task_loop = skill_root / "scripts" / "task_loop.py"

    docs_to_check = [
        skill_root / "README.md",
        skill_root / "SKILL.md",
        skill_root / "references" / "REFERENCE.md",
        skill_root / "references" / "SUBAGENTS.md",
        skill_root / "references" / "COMMANDS.md",
        skill_root / "references" / "SCHEMAS.md",
        skill_root / "agents" / "openai.yaml",
        skill_root / "assets" / "templates" / "managed-block-agents.md.tmpl",
    ]

    frontmatter, body = parse_frontmatter(skill_md)
    missing = sorted(REQUIRED_FRONTMATTER_KEYS - set(frontmatter.keys()))
    if missing:
        raise SystemExit(f"SKILL.md frontmatter missing keys: {', '.join(missing)}")
    if frontmatter["name"] != skill_root.name:
        raise SystemExit("SKILL.md name must match the parent directory name.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", frontmatter["name"]):
        raise SystemExit("SKILL.md name does not match the allowed skill-name pattern.")
    if not body.strip():
        raise SystemExit("SKILL.md body must not be empty.")

    for path in docs_to_check:
        content = path.read_text(encoding="utf-8")
        if "route <TASK_ID>" not in content and "routing.json" not in content:
            raise SystemExit(f"Expected router-v2 documentation markers in {path}")

    if "task-router" not in body or "routing.json" not in body:
        raise SystemExit("SKILL.md should describe task-router and durable routing state.")

    with tempfile.TemporaryDirectory(prefix="repo-task-proof-loop-") as tmp_dir:
        repo = Path(tmp_dir) / "demo-repo"
        repo.mkdir(parents=True)
        run(["git", "init"], repo)

        init_result = run(
            [
                sys.executable,
                str(task_loop),
                "init",
                "--task-id",
                "demo-task",
                "--task-text",
                "Implement a demo task.",
                "--guides",
                "both",
                "--install-subagents",
                "both",
            ],
            repo,
        )
        validate_result = run_no_check(
            [sys.executable, str(task_loop), "validate", "--task-id", "demo-task"],
            repo,
        )
        status_result = run(
            [sys.executable, str(task_loop), "status", "--task-id", "demo-task"],
            repo,
        )

        validate_json = json.loads(validate_result.stdout)
        if validate_result.returncode != 0 or not validate_json.get("valid"):
            raise SystemExit(f"Validation failed: {validate_result.stdout}\n{validate_result.stderr}")

        init_sentinel = repo / ".agent" / "tasks" / "demo-task" / ".init-in-progress"
        init_sentinel.write_text("smoke-test-init-in-progress\n", encoding="utf-8")
        race_validate_result = run_no_check(
            [sys.executable, str(task_loop), "validate", "--task-id", "demo-task"],
            repo,
        )
        race_status_result = run(
            [sys.executable, str(task_loop), "status", "--task-id", "demo-task"],
            repo,
        )
        init_sentinel.unlink()

        race_validate_json = json.loads(race_validate_result.stdout)
        race_status_json = json.loads(race_status_result.stdout)
        if race_validate_result.returncode == 0:
            raise SystemExit("Expected validate to fail while the init sentinel is present.")
        if not race_validate_json.get("init_in_progress"):
            raise SystemExit("Expected validate output to report init_in_progress when the init sentinel is present.")
        if not any("still in progress" in error for error in race_validate_json.get("errors", [])):
            raise SystemExit("Expected validate to report that initialization is still in progress.")
        if not race_status_json.get("init_in_progress"):
            raise SystemExit("Expected status output to report init_in_progress when the init sentinel is present.")

        required_paths = [
            repo / ".agent" / "tasks" / "demo-task" / "spec.md",
            repo / ".agent" / "tasks" / "demo-task" / "routing.json",
            repo / ".agent" / "tasks" / "demo-task" / "dispatches",
            repo / ".agent" / "tasks" / "demo-task" / "evidence.json",
            repo / ".agent" / "tasks" / "demo-task" / "verdict.json",
            repo / ".agent" / "tasks" / "demo-task" / "raw" / "screenshot-1.png",
            repo / ".codex" / "agents" / "task-router.toml",
            repo / ".codex" / "agents" / "task-spec-freezer.toml",
            repo / ".codex" / "agents" / "task-scout.toml",
            repo / ".codex" / "agents" / "task-explorer.toml",
            repo / ".codex" / "agents" / "task-builder.toml",
            repo / ".codex" / "agents" / "task-worker-lite.toml",
            repo / ".codex" / "agents" / "task-worker-strong.toml",
            repo / ".codex" / "agents" / "task-verifier.toml",
            repo / ".codex" / "agents" / "task-fixer.toml",
            repo / ".claude" / "agents" / "task-spec-freezer.md",
            repo / "AGENTS.md",
            repo / "CLAUDE.md",
        ]
        for path in required_paths:
            if not path.exists():
                raise SystemExit(f"Expected path missing after init: {path}")

        managed_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        if "routing.json" not in managed_agents or "task-router.toml" not in managed_agents:
            raise SystemExit("Expected generated AGENTS.md managed block to mention routing.json and task-router.")

        generated_router = (repo / ".codex" / "agents" / "task-router.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.5"' not in generated_router or 'model_reasoning_effort = "medium"' not in generated_router:
            raise SystemExit("Expected generated Codex task-router template to pin gpt-5.5 at medium reasoning.")
        generated_spec_freezer = (repo / ".codex" / "agents" / "task-spec-freezer.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.5"' not in generated_spec_freezer or 'model_reasoning_effort = "low"' not in generated_spec_freezer:
            raise SystemExit("Expected generated Codex task-spec-freezer template to pin gpt-5.5 at low reasoning.")
        generated_builder = (repo / ".codex" / "agents" / "task-builder.toml").read_text(encoding="utf-8")
        if "integration owner" not in generated_builder:
            raise SystemExit("Expected generated Codex task-builder template to describe the integration-owner role.")
        if "model_reasoning_effort" in generated_builder or 'model =' in generated_builder:
            raise SystemExit("Expected generated Codex task-builder template to inherit the parent session model settings.")
        generated_scout = (repo / ".codex" / "agents" / "task-scout.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.4-mini"' not in generated_scout or 'model_reasoning_effort = "low"' not in generated_scout:
            raise SystemExit("Expected generated Codex task-scout template to pin gpt-5.4-mini at low reasoning.")
        generated_explorer = (repo / ".codex" / "agents" / "task-explorer.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.4-mini"' not in generated_explorer or 'model_reasoning_effort = "high"' not in generated_explorer:
            raise SystemExit("Expected generated Codex task-explorer template to pin gpt-5.4-mini at high reasoning.")
        generated_worker_lite = (repo / ".codex" / "agents" / "task-worker-lite.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.4-mini"' not in generated_worker_lite or 'model_reasoning_effort = "medium"' not in generated_worker_lite:
            raise SystemExit("Expected generated Codex task-worker-lite template to pin gpt-5.4-mini at medium reasoning.")
        generated_worker_strong = (repo / ".codex" / "agents" / "task-worker-strong.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.4"' not in generated_worker_strong or 'model_reasoning_effort = "high"' not in generated_worker_strong:
            raise SystemExit("Expected generated Codex task-worker-strong template to pin gpt-5.4 at high reasoning.")
        generated_verifier = (repo / ".codex" / "agents" / "task-verifier.toml").read_text(encoding="utf-8")
        if 'model = "gpt-5.5"' not in generated_verifier or 'model_reasoning_effort = "medium"' not in generated_verifier:
            raise SystemExit("Expected generated Codex task-verifier template to pin gpt-5.5 at medium reasoning.")

        pre_route_result = run(
            [sys.executable, str(task_loop), "route", "--task-id", "demo-task", "--phase", "auto"],
            repo,
        )
        pre_route_json = json.loads(pre_route_result.stdout)
        if pre_route_json.get("route_phase") != "pre-freeze":
            raise SystemExit("Expected initial route call to choose pre-freeze.")
        routed_data = route_json(repo / ".agent" / "tasks" / "demo-task" / "routing.json")
        if routed_data["route_phase"] != "pre-freeze":
            raise SystemExit("Expected routing.json to record a pre-freeze route phase.")
        if any(dispatch["role"] in {"task-builder", "task-worker-lite", "task-worker-strong"} for dispatch in routed_data["planned_dispatches"]):
            raise SystemExit("Pre-freeze route must not schedule write-capable roles.")

        ambiguous_spec = """# Task Spec: demo-task

## Metadata
- Task ID: demo-task

## Guidance sources
- AGENTS.md

## Original task statement
Map which files matter and explain why routing drifts before the spec is frozen.

## Acceptance criteria
- AC1: TODO

## Constraints
- TODO

## Non-goals
- TODO

## Verification plan
- TODO
"""
        write_text(repo / ".agent" / "tasks" / "demo-task" / "spec.md", ambiguous_spec)
        ambiguous_route_result = run(
            [sys.executable, str(task_loop), "route", "--task-id", "demo-task", "--phase", "pre-freeze"],
            repo,
        )
        ambiguous_route_json = json.loads(ambiguous_route_result.stdout)
        if ambiguous_route_json.get("delegation_mode") != "discovery_fanout":
            raise SystemExit("Expected ambiguous pre-freeze route to choose discovery_fanout.")
        ambiguous_routing_data = route_json(repo / ".agent" / "tasks" / "demo-task" / "routing.json")
        roles = {dispatch["role"] for dispatch in ambiguous_routing_data["planned_dispatches"]}
        if not roles or not roles.issubset({"task-scout", "task-explorer"}):
            raise SystemExit("Expected ambiguous pre-freeze route to schedule only task-scout/task-explorer.")
        for dispatch in ambiguous_routing_data["planned_dispatches"]:
            brief = repo / ".agent" / "tasks" / "demo-task" / "dispatches" / f"{dispatch['dispatch_id']}.md"
            if not brief.exists():
                raise SystemExit(f"Expected dispatch brief missing after route: {brief}")

        frozen_spec = """# Task Spec: demo-task

## Metadata
- Task ID: demo-task

## Guidance sources
- AGENTS.md

## Original task statement
Implement a multi-file router refactor with explicit AC ownership hints.

## Acceptance criteria
- AC1: Add the route CLI and durable routing artifacts.
  - Allowed paths: scripts/task_loop.py, assets/templates/routing.json.tmpl
  - No-touch paths: README.md
- AC2: Add router docs and prompt metadata.
  - Allowed paths: SKILL.md, references/COMMANDS.md, agents/openai.yaml
  - No-touch paths: scripts/task_loop.py

## Constraints
- Keep all workflow state inside .agent/tasks/<TASK_ID>/.

## Non-goals
- Do not change Claude compatibility runtime behavior.

## Verification plan
- Build: run smoke tests.
- Unit tests: verify route behavior.
- Integration tests: inspect routing.json and dispatch briefs.
- Lint: keep syntax valid.
- Manual checks: inspect generated agents and docs.
"""
        write_text(repo / ".agent" / "tasks" / "demo-task" / "spec.md", frozen_spec)
        post_route_result = run(
            [sys.executable, str(task_loop), "route", "--task-id", "demo-task", "--phase", "auto"],
            repo,
        )
        post_route_json = json.loads(post_route_result.stdout)
        if post_route_json.get("route_phase") != "post-freeze":
            raise SystemExit("Expected frozen-spec route call to choose post-freeze.")
        if post_route_json.get("delegation_mode") != "implementation_fanout":
            raise SystemExit("Expected frozen multi-file route to choose implementation_fanout.")
        post_routing_data = route_json(repo / ".agent" / "tasks" / "demo-task" / "routing.json")
        dispatch_roles = [dispatch["role"] for dispatch in post_routing_data["planned_dispatches"]]
        if "task-builder" not in dispatch_roles:
            raise SystemExit("Expected post-freeze route to keep a task-builder integration owner.")
        if not any(role in {"task-worker-lite", "task-worker-strong"} for role in dispatch_roles):
            raise SystemExit("Expected post-freeze route to emit worker shards for AC ownership hints.")
        worker_allowed_paths = [
            tuple(dispatch["allowed_paths"])
            for dispatch in post_routing_data["planned_dispatches"]
            if dispatch["role"] in {"task-worker-lite", "task-worker-strong"}
        ]
        if len(worker_allowed_paths) != len(set(worker_allowed_paths)):
            raise SystemExit("Expected worker shard allowed path sets to stay non-overlapping in the smoke test.")
        for dispatch in post_routing_data["planned_dispatches"]:
            brief = repo / ".agent" / "tasks" / "demo-task" / "dispatches" / f"{dispatch['dispatch_id']}.md"
            if not brief.exists():
                raise SystemExit(f"Expected post-freeze dispatch brief missing: {brief}")

        status_after_route = json.loads(
            run([sys.executable, str(task_loop), "status", "--task-id", "demo-task"], repo).stdout
        )
        if status_after_route.get("route_phase") != "post-freeze":
            raise SystemExit("Expected status to report the current route phase.")
        if status_after_route.get("delegation_mode") != "implementation_fanout":
            raise SystemExit("Expected status to report the current delegation mode.")
        if status_after_route.get("planned_dispatch_count", 0) < 2:
            raise SystemExit("Expected status to report planned dispatches after route.")

        malformed_routing = {
            "task_id": "demo-task",
            "policy_version": "router-v2",
            "route_phase": "pre-freeze",
            "delegation_mode": "implementation_fanout",
        }
        write_text(
            repo / ".agent" / "tasks" / "demo-task" / "routing.json",
            json.dumps(malformed_routing, indent=2) + "\n",
        )
        malformed_validate = run_no_check(
            [sys.executable, str(task_loop), "validate", "--task-id", "demo-task"],
            repo,
        )
        malformed_validate_json = json.loads(malformed_validate.stdout)
        if malformed_validate.returncode == 0:
            raise SystemExit("Expected validate to fail on malformed routing.json.")
        if not any("routing.json" in error for error in malformed_validate_json.get("errors", [])):
            raise SystemExit("Expected validate to report routing.json errors for malformed routing state.")

        claude_auto_repo = Path(tmp_dir) / "claude-auto-repo"
        claude_auto_repo.mkdir(parents=True)
        run(["git", "init"], claude_auto_repo)
        (claude_auto_repo / "AGENTS.md").write_text("# Existing AGENTS\n", encoding="utf-8")
        run(
            [
                sys.executable,
                str(task_loop),
                "init",
                "--task-id",
                "demo-task",
                "--task-text",
                "Implement a demo task.",
                "--guides",
                "auto",
                "--install-subagents",
                "claude",
            ],
            claude_auto_repo,
        )
        if not (claude_auto_repo / "CLAUDE.md").exists():
            raise SystemExit("Expected CLAUDE.md to be created for Claude installs in --guides auto mode.")

        codex_auto_repo = Path(tmp_dir) / "codex-auto-repo"
        codex_auto_repo.mkdir(parents=True)
        run(["git", "init"], codex_auto_repo)
        (codex_auto_repo / "CLAUDE.md").write_text("# Existing CLAUDE\n", encoding="utf-8")
        run(
            [
                sys.executable,
                str(task_loop),
                "init",
                "--task-id",
                "demo-task",
                "--task-text",
                "Implement a demo task.",
                "--guides",
                "auto",
                "--install-subagents",
                "codex",
            ],
            codex_auto_repo,
        )
        if not (codex_auto_repo / "AGENTS.md").exists():
            raise SystemExit("Expected AGENTS.md to be created for Codex installs in --guides auto mode.")

        codex_default_repo = Path(tmp_dir) / "codex-default-repo"
        codex_default_repo.mkdir(parents=True)
        run(["git", "init"], codex_default_repo)
        run(
            [
                sys.executable,
                str(task_loop),
                "init",
                "--task-id",
                "demo-task",
                "--task-text",
                "Implement a demo task.",
            ],
            codex_default_repo,
        )
        if not (codex_default_repo / "AGENTS.md").exists():
            raise SystemExit("Expected AGENTS.md to be created by default Codex-only init.")
        if not (codex_default_repo / ".codex" / "agents" / "task-router.toml").exists():
            raise SystemExit("Expected default Codex-only init to install task-router.")
        if (codex_default_repo / "CLAUDE.md").exists() or (codex_default_repo / ".claude" / "agents").exists():
            raise SystemExit("Did not expect Claude guide or agents from default Codex-only init.")

        guidance_repo = Path(tmp_dir) / "guidance-repo"
        guidance_repo.mkdir(parents=True)
        run(["git", "init"], guidance_repo)
        (guidance_repo / "AGENTS.md").write_text("# Root AGENTS\n", encoding="utf-8")
        (guidance_repo / "AGENTS.override.md").write_text("# Root AGENTS override\n", encoding="utf-8")
        nested_rule = guidance_repo / ".claude" / "rules" / "nested" / "workflow.md"
        nested_rule.parent.mkdir(parents=True, exist_ok=True)
        nested_rule.write_text("# Nested workflow rule\n", encoding="utf-8")
        run(
            [
                sys.executable,
                str(task_loop),
                "init",
                "--task-id",
                "demo-task",
                "--task-text",
                "Implement a demo task.",
                "--guides",
                "none",
                "--install-subagents",
                "none",
            ],
            guidance_repo,
        )
        guidance_spec = (guidance_repo / ".agent" / "tasks" / "demo-task" / "spec.md").read_text(encoding="utf-8")
        override_marker = "- AGENTS.override.md"
        agents_marker = "- AGENTS.md"
        rule_marker = "- .claude/rules/nested/workflow.md"
        override_index = guidance_spec.find(override_marker)
        agents_index = guidance_spec.find(agents_marker)
        if override_index == -1 or agents_index == -1:
            raise SystemExit("Expected guidance seeding to include AGENTS.override.md and AGENTS.md.")
        if override_index > agents_index:
            raise SystemExit("Expected AGENTS.override.md to appear before AGENTS.md in seeded guidance.")
        if rule_marker not in guidance_spec:
            raise SystemExit("Expected seeded guidance to include nested .claude/rules/**/*.md files.")

        print(
            json.dumps(
                {
                    "skill_root": str(skill_root),
                    "frontmatter_name": frontmatter["name"],
                    "init_stdout": json.loads(init_result.stdout),
                    "validate_stdout": validate_json,
                    "status_stdout": json.loads(status_result.stdout),
                    "init_race_checks": {
                        "validate_reports_init_in_progress": race_validate_json.get("init_in_progress") is True,
                        "validate_reports_still_in_progress_error": any(
                            "still in progress" in error for error in race_validate_json.get("errors", [])
                        ),
                        "status_reports_init_in_progress": race_status_json.get("init_in_progress") is True,
                    },
                    "route_checks": {
                        "pre_freeze_phase": pre_route_json.get("route_phase"),
                        "ambiguous_pre_freeze_mode": ambiguous_route_json.get("delegation_mode"),
                        "post_freeze_mode": post_route_json.get("delegation_mode"),
                        "post_freeze_dispatch_roles": dispatch_roles,
                    },
                    "claude_auto_guides": {
                        "agents_md": str(claude_auto_repo / "AGENTS.md"),
                        "claude_md": str(claude_auto_repo / "CLAUDE.md"),
                    },
                    "codex_auto_guides": {
                        "agents_md": str(codex_auto_repo / "AGENTS.md"),
                        "claude_md": str(codex_auto_repo / "CLAUDE.md"),
                    },
                    "codex_default_init": {
                        "agents_md": str(codex_default_repo / "AGENTS.md"),
                        "has_claude_md": (codex_default_repo / "CLAUDE.md").exists(),
                    },
                    "guidance_seed_checks": {
                        "override_before_agents": True,
                        "nested_rule_detected": str(nested_rule),
                    },
                    "result": "PASS",
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
