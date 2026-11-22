# Run trace

## What it does
Keeps a record of everything the agent printed, so a run can be inspected after the container
is gone.

## Behaviour
- Every raw stdout line is kept: parsed as JSON when it is JSON, otherwise stored as
  `{"raw": "<line>"}`. No line is dropped.
- When the agent exits, the trace is written as a JSON array to
  `gs://{GCP_PID}-agents-data/coder/{TASK_ID}/trace.json`.
- Writing the trace is best-effort. A failed write is logged and never changes the exit code.

## Where
- `runner/harness/harness.py` — `_trace_entry()`, `_write_trace()`
- `runner/gcp_storage.py` — `put_object()`
- Design: [`concept.md` §3.4](../concept.md#34-observability)
