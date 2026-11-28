# Task resolution

## What it does
Turns a task id into a `TaskSpec`: which repo, which issue, which base branch. The task id
comes from the queued Task Message (queue mode) or from the `TASK_ID` environment variable
(local mode).

## Behaviour
- **Queue mode** (`TASK_ID` unset): the pod pulls one Pub/Sub message. It must be a Toto
  envelope (`{timestamp, cid, id, type, msg, data}`, as totoms publishes it) with
  `type: "taskRequested"` and the id in `data.taskId`. Anything else (not JSON, another type,
  no `data.taskId`, the old raw `{"taskId": "..."}` body) is acked, logged and dropped, and the
  run exits `20`. The envelope's `cid` is logged next to the task id; a missing `cid` is fine.
- **Local mode**: the task id is `TASK_ID`.
- Reads `gs://{GCP_PID}-agents-data/coder/{taskId}/task.json`. The producer (`ape-tasks`)
  writes this file before publishing the message.
- JSON keys are camelCase: `taskId`, `repoURL`, `issueURL` (all required) and `baseBranch`
  (optional, defaults to `main`).
- A missing required field raises a `ValueError`. There is no free-form prompt field: a run
  is always the implementation of one specific issue.

## Where
- `runner/main.py` — `run_queued()`, `resolve_task()`, `agent_bucket()`, `task_object_path()`
- `runner/model/task.py` — `TaskSpec`
- `runner/model/task_message.py` — `TaskMessage` (the queued Toto envelope)
- `runner/gcp_storage.py` — `get_object()`
- Tests: `tests/model/test_task.py`, `tests/model/test_task_message.py`, `tests/test_main.py`
- Design: [`concept.md` §4.1, §4.4](../concept.md#41-taskspec--the-input)
