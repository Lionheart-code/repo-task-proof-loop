# Artifact schemas

These are the required files for each task folder:

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

## `routing.json`

Required top-level keys:

- `task_id`
- `policy_version`
- `route_phase`
- `delegation_mode`
- `complexity`
- `risk_level`
- `authorization_source`
- `assumptions`
- `pending_questions`
- `single_owner_roles`
- `planned_dispatches`
- `updated_at`

Allowed `route_phase` values:

- `unrouted`
- `pre-freeze`
- `post-freeze`

Allowed `delegation_mode` values:

- `serial`
- `discovery_fanout`
- `implementation_fanout`

Each item in `planned_dispatches` must include:

- `dispatch_id`
- `phase`
- `role`
- `objective`
- `ac_ids`
- `allowed_paths`
- `no_touch_paths`
- `input_artifacts`
- `required_output`
- `status`

Recommended shape:

```json
{
  "task_id": "my-task",
  "policy_version": "router-v2",
  "route_phase": "pre-freeze",
  "delegation_mode": "discovery_fanout",
  "complexity": "bounded",
  "risk_level": "medium",
  "authorization_source": "skill-invocation",
  "assumptions": [
    "Prefer the smallest valid decomposition that preserves proof ownership."
  ],
  "pending_questions": [],
  "single_owner_roles": {
    "orchestrator": "parent-session",
    "builder": "task-builder",
    "verifier": "task-verifier"
  },
  "planned_dispatches": [
    {
      "dispatch_id": "dispatch-scout-discovery",
      "phase": "route-pre-freeze",
      "role": "task-scout",
      "objective": "Map the minimum relevant files needed to freeze the spec.",
      "ac_ids": [],
      "allowed_paths": [],
      "no_touch_paths": [],
      "input_artifacts": ["spec.md", "routing.json"],
      "required_output": "Return direct findings and unresolved lookup questions.",
      "status": "planned"
    }
  ],
  "updated_at": "2026-05-08T00:00:00+00:00"
}
```

## Dispatch briefs

The `dispatches/` directory stores one durable Markdown brief per actual child dispatch.

Each brief should capture:

- `dispatch_id`
- phase and role
- objective
- AC scope
- allowed paths
- no-touch paths
- input artifacts
- required output
- guardrails

Treat a dispatch brief plus the frozen `spec.md` as the complete child contract.

## `evidence.json`

Required top-level keys:

- `task_id`
- `overall_status`
- `acceptance_criteria`
- `changed_files`
- `commands_for_fresh_verifier`
- `known_gaps`

Allowed status values:

- `PASS`
- `FAIL`
- `UNKNOWN`

Recommended shape:

```json
{
  "task_id": "my-task",
  "overall_status": "UNKNOWN",
  "acceptance_criteria": [
    {
      "id": "AC1",
      "text": "Describe the criterion",
      "status": "UNKNOWN",
      "proof": [
        {
          "type": "command",
          "path": ".agent/tasks/my-task/raw/test-unit.txt",
          "command": "npm test -- --runInBand",
          "exit_code": 0,
          "summary": "Targeted unit tests passed."
        }
      ],
      "gaps": []
    }
  ],
  "changed_files": [],
  "commands_for_fresh_verifier": [],
  "known_gaps": []
}
```

## `verdict.json`

Required top-level keys:

- `task_id`
- `overall_verdict`
- `criteria`
- `commands_run`
- `artifacts_used`

Allowed status values:

- `PASS`
- `FAIL`
- `UNKNOWN`

Recommended shape:

```json
{
  "task_id": "my-task",
  "overall_verdict": "UNKNOWN",
  "criteria": [
    {
      "id": "AC1",
      "status": "UNKNOWN",
      "reason": "Not yet verified."
    }
  ],
  "commands_run": [],
  "artifacts_used": []
}
```

## `problems.md`

Required sections for each non-`PASS` criterion:

- criterion id and text
- status
- why it is not proven
- minimal reproduction steps
- expected vs actual
- affected files
- smallest safe fix
- corrective hint in 1-3 sentences

## Validation script

Run:

```bash
scripts/task_loop.py validate --task-id <TASK_ID>
```

This checks:

- required file presence
- `routing.json` parseability and schema
- dispatch brief presence for planned dispatches
- JSON parseability
- top-level key presence
- allowed status values
- task id consistency
