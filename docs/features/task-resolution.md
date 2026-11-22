# Task resolution

## What it does
Turns the `TASK_ID` environment variable into a `TaskSpec`: which repo, which issue, which
base branch.

## Behaviour
- Reads `gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json`. The orchestrator writes this
  file before starting the container.
- JSON keys are camelCase: `taskId`, `repoURL`, `issueURL` (all required) and `baseBranch`
  (optional, defaults to `main`).
- A missing required field raises a `ValueError`. There is no free-form prompt field: a run
  is always the implementation of one specific issue.
- `TASK_ID` unset raises a `ValueError`.

## Where
- `runner/main.py` — `resolve_task()`, `agent_bucket()`, `task_object_path()`
- `runner/model/task.py` — `TaskSpec`
- `runner/gcp_storage.py` — `get_object()`
- Tests: `tests/model/test_task.py`
- Design: [`concept.md` §4.1, §4.4](../concept.md#41-taskspec--the-input)
