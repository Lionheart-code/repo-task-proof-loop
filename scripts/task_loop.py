#!/usr/bin/env python3
"""Initialize, route, and validate repo-local task proof loop artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
TEMPLATES_DIR = SKILL_ROOT / "assets" / "templates"

REQUIRED_TASK_ENTRIES: list[tuple[str, str]] = [
    ("spec.md", "file"),
    ("routing.json", "file"),
    ("dispatches", "dir"),
    ("evidence.md", "file"),
    ("evidence.json", "file"),
    ("verdict.json", "file"),
    ("problems.md", "file"),
    ("raw/build.txt", "file"),
    ("raw/test-unit.txt", "file"),
    ("raw/test-integration.txt", "file"),
    ("raw/lint.txt", "file"),
    ("raw/screenshot-1.png", "file"),
]

STATUS_VALUES = {"PASS", "FAIL", "UNKNOWN"}
ROUTE_PHASE_VALUES = {"unrouted", "pre-freeze", "post-freeze"}
ROUTE_PHASE_CHOICES = {"auto", "pre-freeze", "post-freeze"}
DELEGATION_MODE_VALUES = {"serial", "discovery_fanout", "implementation_fanout"}
COMPLEXITY_VALUES = {"trivial", "bounded", "broad", "unknown"}
RISK_LEVEL_VALUES = {"low", "medium", "high", "unknown"}
DISPATCH_STATUS_VALUES = {"planned", "completed", "skipped"}
READ_ONLY_ROUTE_ROLES = {"task-scout", "task-explorer"}
WRITE_CAPABLE_ROUTE_ROLES = {"task-builder", "task-worker-lite", "task-worker-strong", "task-fixer"}
ROUTING_POLICY_VERSION = "router-v2"
INIT_SENTINEL_FILE = ".init-in-progress"

PNG_PLACEHOLDER = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02\x00\x00\x00\x0bIDATx\xdac\xfc"
    b"\xff\x1f\x00\x03\x03\x02\x00\xefe\xf6\xe4\x00\x00\x00\x00IEND\xaeB`\x82"
)

MANAGED_START = "<!-- repo-task-proof-loop:start -->"
MANAGED_END = "<!-- repo-task-proof-loop:end -->"
CODEX_GUIDE_CANDIDATES = (
    Path("AGENTS.override.md"),
    Path("AGENTS.md"),
)
CLAUDE_GUIDE_CANDIDATES = (
    Path("CLAUDE.md"),
    Path(".claude") / "CLAUDE.md",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fail(message: str, exit_code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(exit_code)


def validate_task_id(task_id: str) -> str:
    if not task_id:
        fail("TASK_ID cannot be empty.")
    if "/" in task_id or "\\" in task_id or ".." in task_id:
        fail("TASK_ID must not contain path separators or '..'.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", task_id):
        fail("TASK_ID may contain only letters, numbers, dot, underscore, and hyphen.")
    return task_id


def discover_repo_root(start: Path) -> Path:
    start = start.resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=True,
            capture_output=True,
            text=True,
        )
        git_root = result.stdout.strip()
        if git_root:
            return Path(git_root).resolve()
    except Exception:
        pass

    current = start
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return start
        current = current.parent


def relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())).replace("\\", "/")
    except Exception:
        return str(path.resolve()).replace("\\", "/")


def path_chain(repo_root: Path, current: Path) -> list[Path]:
    repo_root = repo_root.resolve()
    current = current.resolve()
    chain = [repo_root]
    if repo_root == current:
        return chain
    try:
        rel = current.relative_to(repo_root)
    except ValueError:
        return chain
    cursor = repo_root
    for part in rel.parts:
        cursor = cursor / part
        chain.append(cursor)
    return chain


def guidance_candidates_for_directory(directory: Path) -> list[Path]:
    candidates: list[Path] = []
    for rel_path in (*CODEX_GUIDE_CANDIDATES, Path("CLAUDE.md"), Path(".claude") / "CLAUDE.md"):
        candidate = directory / rel_path
        if candidate.exists():
            candidates.append(candidate)

    rules_dir = directory / ".claude" / "rules"
    if rules_dir.is_dir():
        for candidate in sorted(path for path in rules_dir.rglob("*.md") if path.is_file()):
            if candidate.is_file():
                candidates.append(candidate)

    return candidates


def discover_guidance_files(repo_root: Path, current: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in path_chain(repo_root, current):
        for candidate in guidance_candidates_for_directory(directory):
            if candidate.exists():
                resolved = candidate.resolve()
                if resolved not in seen:
                    found.append(candidate)
                    seen.add(resolved)
    return found


def load_text_template(name: str) -> str:
    path = TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


def render_template(text: str, mapping: dict[str, str]) -> str:
    rendered = text
    for key, value in mapping.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def init_sentinel_path(task_dir: Path) -> Path:
    return task_dir / INIT_SENTINEL_FILE


def mark_init_in_progress(task_dir: Path) -> None:
    sentinel = init_sentinel_path(task_dir)
    sentinel.write_text(f"{utc_now_iso()}\n", encoding="utf-8")


def clear_init_in_progress(task_dir: Path) -> None:
    sentinel = init_sentinel_path(task_dir)
    try:
        sentinel.unlink()
    except FileNotFoundError:
        pass


def has_managed_block(path: Path) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    return MANAGED_START in content and MANAGED_END in content


def write_text_file(path: Path, content: str, *, force: bool = False) -> bool:
    ensure_parent(path)
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def write_binary_file(path: Path, content: bytes, *, force: bool = False) -> bool:
    ensure_parent(path)
    if path.exists() and not force:
        return False
    path.write_bytes(content)
    return True


def upsert_managed_block(path: Path, block: str) -> str:
    ensure_parent(path)
    if path.exists():
        content = path.read_text(encoding="utf-8")
    else:
        content = ""

    if MANAGED_START in content and MANAGED_END in content:
        pattern = re.compile(
            re.escape(MANAGED_START) + r".*?" + re.escape(MANAGED_END),
            re.DOTALL,
        )
        new_content = pattern.sub(block.strip(), content).rstrip() + "\n"
        action = "updated"
    else:
        if content.strip():
            new_content = content.rstrip() + "\n\n" + block.strip() + "\n"
        else:
            new_content = block.strip() + "\n"
        action = "created" if not path.exists() else "appended"

    path.write_text(new_content, encoding="utf-8")
    return action


def placeholder_task_statement(task_file: str | None, task_text: str | None) -> str:
    if task_text:
        return task_text.strip()
    if task_file:
        try:
            return Path(task_file).read_text(encoding="utf-8").strip()
        except Exception as exc:
            return f"Unable to read task file `{task_file}` at init time: {exc}"
    return "TODO: paste or summarize the original user task here."


def guidance_bullets(repo_root: Path, current: Path) -> str:
    discovered = discover_guidance_files(repo_root, current)
    if not discovered:
        return "- None detected at init time."
    return "\n".join(f"- {relative_or_absolute(path, repo_root)}" for path in discovered)


def choose_claude_guide_path(repo_root: Path) -> Path:
    for rel_path in CLAUDE_GUIDE_CANDIDATES:
        candidate = repo_root / rel_path
        if has_managed_block(candidate):
            return candidate
    for rel_path in CLAUDE_GUIDE_CANDIDATES:
        candidate = repo_root / rel_path
        if candidate.exists():
            return candidate
    return repo_root / "CLAUDE.md"


def template_context(task_id: str, repo_root: Path, current: Path, task_file: str | None, task_text: str | None) -> dict[str, str]:
    return {
        "TASK_ID": task_id,
        "CREATED_AT": utc_now_iso(),
        "UPDATED_AT": utc_now_iso(),
        "REPO_ROOT": str(repo_root.resolve()),
        "WORKING_DIR": str(current.resolve()),
        "GUIDANCE_SOURCES": guidance_bullets(repo_root, current),
        "TASK_STATEMENT": placeholder_task_statement(task_file, task_text),
    }


def install_task_files(task_dir: Path, context: dict[str, str], *, force: bool = False) -> list[str]:
    created: list[str] = []

    file_map = {
        task_dir / "spec.md": render_template(load_text_template("spec.md.tmpl"), context),
        task_dir / "routing.json": render_template(load_text_template("routing.json.tmpl"), context),
        task_dir / "evidence.md": render_template(load_text_template("evidence.md.tmpl"), context),
        task_dir / "evidence.json": render_template(load_text_template("evidence.json.tmpl"), context),
        task_dir / "verdict.json": render_template(load_text_template("verdict.json.tmpl"), context),
        task_dir / "problems.md": render_template(load_text_template("problems.md.tmpl"), context),
        task_dir / "raw" / "build.txt": load_text_template("raw.build.txt.tmpl"),
        task_dir / "raw" / "test-unit.txt": load_text_template("raw.test-unit.txt.tmpl"),
        task_dir / "raw" / "test-integration.txt": load_text_template("raw.test-integration.txt.tmpl"),
        task_dir / "raw" / "lint.txt": load_text_template("raw.lint.txt.tmpl"),
    }

    for path, content in file_map.items():
        if write_text_file(path, content, force=force):
            created.append(str(path))

    screenshot = task_dir / "raw" / "screenshot-1.png"
    if write_binary_file(screenshot, PNG_PLACEHOLDER, force=force):
        created.append(str(screenshot))

    dispatches_dir = task_dir / "dispatches"
    dispatches_dir.mkdir(parents=True, exist_ok=True)
    if str(dispatches_dir) not in created:
        created.append(str(dispatches_dir))

    return created


def install_codex_agents(repo_root: Path) -> list[str]:
    target_dir = repo_root / ".codex" / "agents"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for template_name in (
        "task-router.toml.tmpl",
        "task-spec-freezer.toml.tmpl",
        "task-scout.toml.tmpl",
        "task-explorer.toml.tmpl",
        "task-builder.toml.tmpl",
        "task-worker-lite.toml.tmpl",
        "task-worker-strong.toml.tmpl",
        "task-verifier.toml.tmpl",
        "task-fixer.toml.tmpl",
    ):
        content = (TEMPLATES_DIR / "codex" / template_name).read_text(encoding="utf-8")
        target = target_dir / template_name.replace(".tmpl", "")
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def install_claude_agents(repo_root: Path) -> list[str]:
    target_dir = repo_root / ".claude" / "agents"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for template_name in (
        "task-spec-freezer.md.tmpl",
        "task-builder.md.tmpl",
        "task-verifier.md.tmpl",
        "task-fixer.md.tmpl",
    ):
        content = (TEMPLATES_DIR / "claude" / template_name).read_text(encoding="utf-8")
        target = target_dir / template_name.replace(".tmpl", "")
        target.write_text(content, encoding="utf-8")
        written.append(str(target))
    return written


def update_guides(repo_root: Path, guides: str, install_subagents: str) -> dict[str, str]:
    actions: dict[str, str] = {}
    if guides == "none":
        return actions

    agents_guide = repo_root / "AGENTS.md"
    claude_guide = choose_claude_guide_path(repo_root)
    existing_claude_guides = [
        repo_root / rel_path
        for rel_path in CLAUDE_GUIDE_CANDIDATES
        if (repo_root / rel_path).exists()
    ]

    want_codex = install_subagents in {"both", "codex"}
    want_claude = install_subagents in {"both", "claude"}

    include_agents = guides in {"both", "agents"}
    include_claude = guides in {"both", "claude"}

    if guides == "auto":
        include_agents = agents_guide.exists()
        include_claude = bool(existing_claude_guides)

        if want_codex and not include_agents:
            include_agents = True
        if want_claude and not include_claude:
            include_claude = True

        if not include_agents and not include_claude:
            include_agents = True
            include_claude = True

    guide_targets: list[tuple[Path, str]] = []
    if include_agents:
        guide_targets.append((agents_guide, load_text_template("managed-block-agents.md.tmpl")))
    if include_claude:
        guide_targets.append((claude_guide, load_text_template("managed-block-claude.md.tmpl")))

    for path, template in guide_targets:
        action = upsert_managed_block(path, template)
        actions[str(path)] = action

    return actions


def json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def task_entry_exists(task_dir: Path, rel_path: str, kind: str) -> bool:
    target = task_dir / rel_path
    if kind == "file":
        return target.is_file()
    if kind == "dir":
        return target.is_dir()
    raise ValueError(f"Unsupported task entry kind: {kind}")


def read_task_text(task_dir: Path, rel_path: str) -> str:
    return (task_dir / rel_path).read_text(encoding="utf-8")


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_acceptance_criteria(spec_text: str) -> list[dict[str, Any]]:
    section = extract_markdown_section(spec_text, "Acceptance criteria")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in section.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"-\s+(AC\d+):\s+(.*)", line)
        if match:
            current = {
                "id": match.group(1),
                "text": match.group(2).strip(),
                "notes": [],
            }
            entries.append(current)
            continue
        if current and line.startswith("  - "):
            current["notes"].append(line[4:].strip())
        elif current and line.startswith("    "):
            note_lines = current["notes"]
            if note_lines:
                note_lines[-1] = f"{note_lines[-1]} {line.strip()}".strip()
    return entries


def parse_csv_like_list(text: str) -> list[str]:
    if not text.strip():
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def extract_note_value(notes: list[str], label: str) -> list[str]:
    prefix = f"{label}:"
    for note in notes:
        if note.lower().startswith(prefix.lower()):
            return parse_csv_like_list(note.split(":", 1)[1].strip())
    return []


def derive_route_hints(ac: dict[str, Any]) -> tuple[list[str], list[str], str | None]:
    notes = ac.get("notes", [])
    allowed_paths = extract_note_value(notes, "Allowed paths")
    no_touch_paths = extract_note_value(notes, "No-touch paths")
    required_output_values = extract_note_value(notes, "Required output")
    required_output = required_output_values[0] if required_output_values else None
    return allowed_paths, no_touch_paths, required_output


def spec_is_frozen(spec_text: str) -> bool:
    criteria = parse_acceptance_criteria(spec_text)
    if not criteria:
        return False
    if any("TODO" in item["text"] for item in criteria):
        return False
    constraints = extract_markdown_section(spec_text, "Constraints")
    non_goals = extract_markdown_section(spec_text, "Non-goals")
    verification_plan = extract_markdown_section(spec_text, "Verification plan")
    if any("TODO" in section for section in (constraints, non_goals, verification_plan)):
        return False
    return True


def detect_complexity(text: str, criteria_count: int) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("migration", "cross-file", "multi-file", "architecture", "broad", "orchestr")):
        return "broad"
    if criteria_count <= 1 and len(lowered) < 220:
        return "trivial"
    if criteria_count >= 3 or "fan-out" in lowered or "parallel" in lowered:
        return "broad"
    return "bounded"


def detect_risk_level(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("migration", "security", "verification", "critical", "high-risk", "judge")):
        return "high"
    if any(marker in lowered for marker in ("routing", "subagent", "parallel", "fan-out", "integration")):
        return "medium"
    return "low"


def pending_questions_for_spec(spec_text: str) -> list[str]:
    questions: list[str] = []
    if "TODO" in extract_markdown_section(spec_text, "Acceptance criteria"):
        questions.append("Acceptance criteria still contain TODO markers.")
    if "TODO" in extract_markdown_section(spec_text, "Constraints"):
        questions.append("Constraints still contain TODO markers.")
    if "TODO" in extract_markdown_section(spec_text, "Non-goals"):
        questions.append("Non-goals still contain TODO markers.")
    if not spec_is_frozen(spec_text):
        questions.append("Spec is not yet frozen; write-capable children must wait.")
    return questions


def karpathy_assumptions(route_phase: str) -> list[str]:
    assumptions = [
        "Prefer the smallest valid decomposition that still preserves proof ownership.",
        "Each child brief should answer one question or own one implementation shard.",
        "Do not broaden scope beyond frozen acceptance criteria.",
    ]
    if route_phase == "pre-freeze":
        assumptions.append("Before freeze, routing may only schedule read-only discovery roles.")
    return assumptions


def task_statement_from_spec(spec_text: str) -> str:
    return extract_markdown_section(spec_text, "Original task statement")


def spec_summary_text(spec_text: str) -> str:
    return "\n".join(
        part
        for part in (
            task_statement_from_spec(spec_text),
            extract_markdown_section(spec_text, "Acceptance criteria"),
            extract_markdown_section(spec_text, "Constraints"),
        )
        if part
    )


def build_dispatch_brief(task_id: str, dispatch: dict[str, Any]) -> str:
    allowed_paths = dispatch["allowed_paths"] or ["(inherit from parent or repo-wide scope)"]
    no_touch_paths = dispatch["no_touch_paths"] or ["(none)"]
    input_artifacts = dispatch["input_artifacts"] or ["spec.md"]
    ac_ids = dispatch["ac_ids"] or ["(not scoped to a single AC)"]
    return "\n".join(
        [
            f"# Dispatch Brief: {dispatch['dispatch_id']}",
            "",
            f"- Task ID: {task_id}",
            f"- Phase: {dispatch['phase']}",
            f"- Role: {dispatch['role']}",
            f"- Status: {dispatch['status']}",
            "",
            "## Objective",
            dispatch["objective"],
            "",
            "## Acceptance criteria scope",
            *[f"- {item}" for item in ac_ids],
            "",
            "## Allowed paths",
            *[f"- {item}" for item in allowed_paths],
            "",
            "## No-touch paths",
            *[f"- {item}" for item in no_touch_paths],
            "",
            "## Input artifacts",
            *[f"- {item}" for item in input_artifacts],
            "",
            "## Required output",
            f"- {dispatch['required_output']}",
            "",
            "## Guardrails",
            "- Treat this brief plus the frozen spec as the complete task contract.",
            "- State assumptions explicitly instead of guessing.",
            "- Prefer the smallest defensible change or finding set.",
            "- Do not broaden scope beyond the objective and AC subset above.",
        ]
    ) + "\n"


def remove_stale_dispatch_briefs(dispatches_dir: Path) -> None:
    for path in dispatches_dir.glob("dispatch-*.md"):
        path.unlink()


def write_dispatch_briefs(task_dir: Path, task_id: str, dispatches: list[dict[str, Any]]) -> list[str]:
    dispatches_dir = task_dir / "dispatches"
    dispatches_dir.mkdir(parents=True, exist_ok=True)
    remove_stale_dispatch_briefs(dispatches_dir)
    written: list[str] = []
    for dispatch in dispatches:
        path = dispatches_dir / f"{dispatch['dispatch_id']}.md"
        path.write_text(build_dispatch_brief(task_id, dispatch), encoding="utf-8")
        written.append(str(path))
    return written


def route_pre_freeze(task_id: str, spec_text: str) -> tuple[str, list[dict[str, Any]]]:
    summary = spec_summary_text(spec_text).lower()
    discovery_dispatches: list[dict[str, Any]] = []
    if any(token in summary for token in ("where", "which", "map", "ownership", "lookup", "tests", "config")):
        discovery_dispatches.append(
            {
                "dispatch_id": "dispatch-scout-discovery",
                "phase": "route-pre-freeze",
                "role": "task-scout",
                "objective": "Map the minimum relevant files, tests, configs, and ownership signals needed to freeze the spec.",
                "ac_ids": [],
                "allowed_paths": [],
                "no_touch_paths": [],
                "input_artifacts": ["spec.md", "routing.json"],
                "required_output": "Return direct findings, relevant paths, and unresolved lookup questions for the spec freezer.",
                "status": "planned",
            }
        )
    if any(token in summary for token in ("why", "trace", "flow", "contract", "invariant", "causality", "drift", "route")):
        discovery_dispatches.append(
            {
                "dispatch_id": "dispatch-explorer-tracing",
                "phase": "route-pre-freeze",
                "role": "task-explorer",
                "objective": "Trace the real execution path, contracts, and invariants needed to freeze the spec without guessing.",
                "ac_ids": [],
                "allowed_paths": [],
                "no_touch_paths": [],
                "input_artifacts": ["spec.md", "routing.json"],
                "required_output": "Return concrete execution facts, invariants, and risks that change the frozen spec.",
                "status": "planned",
            }
        )
    if discovery_dispatches:
        return "discovery_fanout", discovery_dispatches[:3]
    return "serial", []


def worker_role_for_ac(text: str, allowed_paths: list[str]) -> str:
    lowered = text.lower()
    if len(allowed_paths) > 1 or any(token in lowered for token in ("multi-file", "risk", "migration", "integration", "router", "verifier")):
        return "task-worker-strong"
    return "task-worker-lite"


def route_post_freeze(task_id: str, spec_text: str) -> tuple[str, list[dict[str, Any]]]:
    criteria = parse_acceptance_criteria(spec_text)
    dispatches: list[dict[str, Any]] = [
        {
            "dispatch_id": "dispatch-task-builder-integration",
            "phase": "build",
            "role": "task-builder",
            "objective": "Act as the single integration owner, implement against the frozen spec, and retain evidence ownership.",
            "ac_ids": [item["id"] for item in criteria],
            "allowed_paths": [],
            "no_touch_paths": [],
            "input_artifacts": ["spec.md", "routing.json"],
            "required_output": "Implement the frozen task, integrate sibling findings if any, and keep evidence ownership with the builder.",
            "status": "planned",
        }
    ]

    worker_dispatches: list[dict[str, Any]] = []
    for item in criteria:
        allowed_paths, no_touch_paths, required_output = derive_route_hints(item)
        if not allowed_paths:
            continue
        worker_dispatches.append(
            {
                "dispatch_id": f"dispatch-{item['id'].lower()}",
                "phase": "build",
                "role": worker_role_for_ac(item["text"], allowed_paths),
                "objective": item["text"],
                "ac_ids": [item["id"]],
                "allowed_paths": allowed_paths,
                "no_touch_paths": no_touch_paths,
                "input_artifacts": ["spec.md", "routing.json"],
                "required_output": required_output or "Return files changed, checks run, and residual risks for the scoped AC shard.",
                "status": "planned",
            }
        )

    if worker_dispatches:
        dispatches.extend(worker_dispatches)
        return "implementation_fanout", dispatches
    return "serial", dispatches


def build_routing_data(task_id: str, spec_text: str, requested_phase: str) -> dict[str, Any]:
    criteria = parse_acceptance_criteria(spec_text)
    summary = spec_summary_text(spec_text)
    route_phase = requested_phase
    if requested_phase == "auto":
        route_phase = "post-freeze" if spec_is_frozen(spec_text) else "pre-freeze"

    delegation_mode, planned_dispatches = (
        route_pre_freeze(task_id, spec_text)
        if route_phase == "pre-freeze"
        else route_post_freeze(task_id, spec_text)
    )

    return {
        "task_id": task_id,
        "policy_version": ROUTING_POLICY_VERSION,
        "route_phase": route_phase,
        "delegation_mode": delegation_mode,
        "complexity": detect_complexity(summary, len(criteria)),
        "risk_level": detect_risk_level(summary),
        "authorization_source": "skill-invocation",
        "assumptions": karpathy_assumptions(route_phase),
        "pending_questions": pending_questions_for_spec(spec_text),
        "single_owner_roles": {
            "orchestrator": "parent-session",
            "builder": "task-builder",
            "verifier": "task-verifier",
        },
        "planned_dispatches": planned_dispatches,
        "updated_at": utc_now_iso(),
    }


def validate_evidence(data: Any, task_id: str) -> list[str]:
    errors: list[str] = []
    required_keys = {
        "task_id",
        "overall_status",
        "acceptance_criteria",
        "changed_files",
        "commands_for_fresh_verifier",
        "known_gaps",
    }
    if not isinstance(data, dict):
        return ["evidence.json must contain a JSON object."]
    missing = sorted(required_keys - set(data.keys()))
    if missing:
        errors.append(f"evidence.json missing keys: {', '.join(missing)}")
    if data.get("task_id") != task_id:
        errors.append("evidence.json task_id does not match the requested TASK_ID.")
    if data.get("overall_status") not in STATUS_VALUES:
        errors.append("evidence.json overall_status must be PASS, FAIL, or UNKNOWN.")
    criteria = data.get("acceptance_criteria")
    if not isinstance(criteria, list):
        errors.append("evidence.json acceptance_criteria must be a list.")
    else:
        for index, item in enumerate(criteria):
            if not isinstance(item, dict):
                errors.append(f"evidence.json acceptance_criteria[{index}] must be an object.")
                continue
            for key in ("id", "text", "status", "proof", "gaps"):
                if key not in item:
                    errors.append(f"evidence.json acceptance_criteria[{index}] missing key: {key}")
            if item.get("status") not in STATUS_VALUES:
                errors.append(f"evidence.json acceptance_criteria[{index}].status must be PASS, FAIL, or UNKNOWN.")
    return errors


def validate_verdict(data: Any, task_id: str) -> list[str]:
    errors: list[str] = []
    required_keys = {"task_id", "overall_verdict", "criteria", "commands_run", "artifacts_used"}
    if not isinstance(data, dict):
        return ["verdict.json must contain a JSON object."]
    missing = sorted(required_keys - set(data.keys()))
    if missing:
        errors.append(f"verdict.json missing keys: {', '.join(missing)}")
    if data.get("task_id") != task_id:
        errors.append("verdict.json task_id does not match the requested TASK_ID.")
    if data.get("overall_verdict") not in STATUS_VALUES:
        errors.append("verdict.json overall_verdict must be PASS, FAIL, or UNKNOWN.")
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        errors.append("verdict.json criteria must be a list.")
    else:
        for index, item in enumerate(criteria):
            if not isinstance(item, dict):
                errors.append(f"verdict.json criteria[{index}] must be an object.")
                continue
            for key in ("id", "status", "reason"):
                if key not in item:
                    errors.append(f"verdict.json criteria[{index}] missing key: {key}")
            if item.get("status") not in STATUS_VALUES:
                errors.append(f"verdict.json criteria[{index}].status must be PASS, FAIL, or UNKNOWN.")
    return errors


def validate_routing(data: Any, task_id: str, task_dir: Path) -> list[str]:
    errors: list[str] = []
    required_keys = {
        "task_id",
        "policy_version",
        "route_phase",
        "delegation_mode",
        "complexity",
        "risk_level",
        "authorization_source",
        "assumptions",
        "pending_questions",
        "single_owner_roles",
        "planned_dispatches",
        "updated_at",
    }
    dispatch_required_keys = {
        "dispatch_id",
        "phase",
        "role",
        "objective",
        "ac_ids",
        "allowed_paths",
        "no_touch_paths",
        "input_artifacts",
        "required_output",
        "status",
    }
    if not isinstance(data, dict):
        return ["routing.json must contain a JSON object."]
    missing = sorted(required_keys - set(data.keys()))
    if missing:
        errors.append(f"routing.json missing keys: {', '.join(missing)}")
    if data.get("task_id") != task_id:
        errors.append("routing.json task_id does not match the requested TASK_ID.")
    if data.get("route_phase") not in ROUTE_PHASE_VALUES:
        errors.append("routing.json route_phase must be unrouted, pre-freeze, or post-freeze.")
    if data.get("delegation_mode") not in DELEGATION_MODE_VALUES:
        errors.append("routing.json delegation_mode must be serial, discovery_fanout, or implementation_fanout.")
    if data.get("complexity") not in COMPLEXITY_VALUES:
        errors.append("routing.json complexity must be trivial, bounded, broad, or unknown.")
    if data.get("risk_level") not in RISK_LEVEL_VALUES:
        errors.append("routing.json risk_level must be low, medium, high, or unknown.")
    if not isinstance(data.get("assumptions"), list):
        errors.append("routing.json assumptions must be a list.")
    if not isinstance(data.get("pending_questions"), list):
        errors.append("routing.json pending_questions must be a list.")
    if not isinstance(data.get("single_owner_roles"), dict):
        errors.append("routing.json single_owner_roles must be an object.")
    planned_dispatches = data.get("planned_dispatches")
    if not isinstance(planned_dispatches, list):
        errors.append("routing.json planned_dispatches must be a list.")
        planned_dispatches = []
    dispatches_dir = task_dir / "dispatches"
    for index, item in enumerate(planned_dispatches):
        if not isinstance(item, dict):
            errors.append(f"routing.json planned_dispatches[{index}] must be an object.")
            continue
        missing_dispatch_keys = sorted(dispatch_required_keys - set(item.keys()))
        if missing_dispatch_keys:
            errors.append(
                f"routing.json planned_dispatches[{index}] missing keys: {', '.join(missing_dispatch_keys)}"
            )
        if item.get("status") not in DISPATCH_STATUS_VALUES:
            errors.append(
                f"routing.json planned_dispatches[{index}].status must be planned, completed, or skipped."
            )
        role = item.get("role")
        if data.get("route_phase") == "pre-freeze" and role in WRITE_CAPABLE_ROUTE_ROLES:
            errors.append("routing.json pre-freeze routing must not schedule write-capable roles.")
        if data.get("route_phase") == "pre-freeze" and role not in READ_ONLY_ROUTE_ROLES:
            errors.append("routing.json pre-freeze routing may only schedule task-scout or task-explorer.")
        dispatch_id = item.get("dispatch_id")
        if isinstance(dispatch_id, str) and dispatch_id:
            brief_path = dispatches_dir / f"{dispatch_id}.md"
            if not brief_path.exists():
                errors.append(f"Dispatch brief missing for {dispatch_id}: {brief_path}")
    return errors


def cmd_init(args: argparse.Namespace) -> int:
    current = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    repo_root = discover_repo_root(current)
    task_id = validate_task_id(args.task_id)
    task_dir = repo_root / ".agent" / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    mark_init_in_progress(task_dir)
    try:
        context = template_context(task_id, repo_root, current, args.task_file, args.task_text)
        created_files = install_task_files(task_dir, context, force=args.force)

        installed_agents: list[str] = []
        if args.install_subagents in {"both", "codex"}:
            installed_agents.extend(install_codex_agents(repo_root))
        if args.install_subagents in {"both", "claude"}:
            installed_agents.extend(install_claude_agents(repo_root))

        guide_actions = update_guides(repo_root, args.guides, args.install_subagents)

        result = {
            "repo_root": str(repo_root),
            "task_id": task_id,
            "task_dir": str(task_dir),
            "created_or_overwritten_task_files": created_files,
            "installed_or_refreshed_subagent_files": installed_agents,
            "guide_file_actions": guide_actions,
        }
        print(json.dumps(result, indent=2))
        return 0
    finally:
        clear_init_in_progress(task_dir)


def cmd_route(args: argparse.Namespace) -> int:
    current = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    repo_root = discover_repo_root(current)
    task_id = validate_task_id(args.task_id)
    task_dir = repo_root / ".agent" / "tasks" / task_id

    if not task_dir.exists():
        fail(f"Task directory does not exist: {task_dir}")
    if init_sentinel_path(task_dir).exists():
        fail("Task initialization is still in progress. Rerun route after init completes.")

    spec_path = task_dir / "spec.md"
    if not spec_path.exists():
        fail(f"Missing spec.md for TASK_ID {task_id}: {spec_path}")

    spec_text = spec_path.read_text(encoding="utf-8")
    routing = build_routing_data(task_id, spec_text, args.phase)
    routing_path = task_dir / "routing.json"
    routing_path.write_text(json.dumps(routing, indent=2) + "\n", encoding="utf-8")
    written_dispatches = write_dispatch_briefs(task_dir, task_id, routing["planned_dispatches"])

    result = {
        "repo_root": str(repo_root),
        "task_id": task_id,
        "task_dir": str(task_dir),
        "route_phase": routing["route_phase"],
        "delegation_mode": routing["delegation_mode"],
        "complexity": routing["complexity"],
        "risk_level": routing["risk_level"],
        "planned_dispatch_count": len(routing["planned_dispatches"]),
        "dispatch_briefs": written_dispatches,
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    current = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    repo_root = discover_repo_root(current)
    task_id = validate_task_id(args.task_id)
    task_dir = repo_root / ".agent" / "tasks" / task_id

    missing = [
        str(task_dir / rel_path)
        for rel_path, kind in REQUIRED_TASK_ENTRIES
        if not task_entry_exists(task_dir, rel_path, kind)
    ]
    errors: list[str] = []
    init_in_progress = init_sentinel_path(task_dir).exists()

    if not task_dir.exists():
        errors.append(f"Task directory does not exist: {task_dir}")
    elif init_in_progress:
        errors.append(
            f"Task initialization is still in progress: {init_sentinel_path(task_dir)}. "
            "Rerun validate after init completes."
        )

    routing_path = task_dir / "routing.json"
    evidence_path = task_dir / "evidence.json"
    verdict_path = task_dir / "verdict.json"

    if routing_path.exists():
        try:
            routing = json_load(routing_path)
            errors.extend(validate_routing(routing, task_id, task_dir))
        except Exception as exc:
            errors.append(f"Failed to parse routing.json: {exc}")

    if evidence_path.exists():
        try:
            evidence = json_load(evidence_path)
            errors.extend(validate_evidence(evidence, task_id))
        except Exception as exc:
            errors.append(f"Failed to parse evidence.json: {exc}")

    if verdict_path.exists():
        try:
            verdict = json_load(verdict_path)
            errors.extend(validate_verdict(verdict, task_id))
        except Exception as exc:
            errors.append(f"Failed to parse verdict.json: {exc}")

    valid = not missing and not errors
    report = {
        "repo_root": str(repo_root),
        "task_id": task_id,
        "task_dir": str(task_dir),
        "init_in_progress": init_in_progress,
        "valid": valid,
        "missing_files": missing,
        "errors": errors,
    }
    print(json.dumps(report, indent=2))
    return 0 if valid else 1


def cmd_status(args: argparse.Namespace) -> int:
    current = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    repo_root = discover_repo_root(current)
    task_id = validate_task_id(args.task_id)
    task_dir = repo_root / ".agent" / "tasks" / task_id

    report: dict[str, Any] = {
        "repo_root": str(repo_root),
        "task_id": task_id,
        "task_dir": str(task_dir),
        "exists": task_dir.exists(),
        "init_in_progress": init_sentinel_path(task_dir).exists(),
        "required_files_present": {},
        "routing_ready": False,
        "route_phase": None,
        "delegation_mode": None,
        "planned_dispatch_count": 0,
        "evidence_overall_status": None,
        "verdict_overall_status": None,
        "non_pass_criteria": [],
    }

    for rel_path, kind in REQUIRED_TASK_ENTRIES:
        key = f"{rel_path}/" if kind == "dir" else rel_path
        report["required_files_present"][key] = task_entry_exists(task_dir, rel_path, kind)

    routing_path = task_dir / "routing.json"
    if routing_path.exists():
        try:
            routing = json_load(routing_path)
            report["routing_ready"] = bool(routing.get("route_phase")) and routing.get("route_phase") != "unrouted"
            report["route_phase"] = routing.get("route_phase")
            report["delegation_mode"] = routing.get("delegation_mode")
            planned_dispatches = routing.get("planned_dispatches", [])
            report["planned_dispatch_count"] = len(planned_dispatches) if isinstance(planned_dispatches, list) else 0
        except Exception as exc:
            report["route_phase"] = f"PARSE_ERROR: {exc}"

    evidence_path = task_dir / "evidence.json"
    if evidence_path.exists():
        try:
            evidence = json_load(evidence_path)
            report["evidence_overall_status"] = evidence.get("overall_status")
        except Exception as exc:
            report["evidence_overall_status"] = f"PARSE_ERROR: {exc}"

    verdict_path = task_dir / "verdict.json"
    if verdict_path.exists():
        try:
            verdict = json_load(verdict_path)
            report["verdict_overall_status"] = verdict.get("overall_verdict")
            criteria = verdict.get("criteria", [])
            if isinstance(criteria, list):
                for item in criteria:
                    if isinstance(item, dict) and item.get("status") in {"FAIL", "UNKNOWN"}:
                        report["non_pass_criteria"].append(
                            {
                                "id": item.get("id"),
                                "status": item.get("status"),
                                "reason": item.get("reason"),
                            }
                        )
        except Exception as exc:
            report["verdict_overall_status"] = f"PARSE_ERROR: {exc}"

    print(json.dumps(report, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repo task proof loop helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize repo-local task artifacts and integration files.")
    init_parser.add_argument("--task-id", required=True, help="Task identifier, e.g. feature-auth-hardening")
    init_parser.add_argument("--task-file", help="Optional path to a task description file to seed spec.md")
    init_parser.add_argument("--task-text", help="Optional inline task text to seed spec.md")
    init_parser.add_argument("--repo-root", help="Optional working directory inside the repo. Defaults to the current directory.")
    init_parser.add_argument(
        "--guides",
        choices=["auto", "agents", "claude", "both", "none"],
        default="auto",
        help="Which guide files to create or update.",
    )
    init_parser.add_argument(
        "--install-subagents",
        choices=["both", "codex", "claude", "none"],
        default="codex",
        help="Which project-scoped subagent sets to install or refresh.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing task artifact templates.")
    init_parser.set_defaults(func=cmd_init)

    route_parser = subparsers.add_parser("route", help="Produce or refresh durable routing state for a task.")
    route_parser.add_argument("--task-id", required=True, help="Task identifier to route.")
    route_parser.add_argument("--repo-root", help="Optional working directory inside the repo. Defaults to the current directory.")
    route_parser.add_argument(
        "--phase",
        choices=sorted(ROUTE_PHASE_CHOICES),
        default="auto",
        help="Routing pass to run. auto infers pre-freeze vs post-freeze from spec.md.",
    )
    route_parser.set_defaults(func=cmd_route)

    validate_parser = subparsers.add_parser("validate", help="Validate required task files and JSON structures.")
    validate_parser.add_argument("--task-id", required=True, help="Task identifier to validate.")
    validate_parser.add_argument("--repo-root", help="Optional working directory inside the repo. Defaults to the current directory.")
    validate_parser.set_defaults(func=cmd_validate)

    status_parser = subparsers.add_parser("status", help="Summarize current task artifact status.")
    status_parser.add_argument("--task-id", required=True, help="Task identifier to summarize.")
    status_parser.add_argument("--repo-root", help="Optional working directory inside the repo. Defaults to the current directory.")
    status_parser.set_defaults(func=cmd_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
