# Agent run

## What it does
Runs the agent CLI (Claude Code today) against the cloned repo and returns its exit code as
the container's exit code.

## Behaviour
- The prompt is fixed: `/implement issue <issueURL>`. Only the issue varies between runs.
- The command runs with the clone as its working directory, in an environment made of the
  container's own, the harness's variables, and `GH_TOKEN`.
- Each stdout line is parsed and the LLM's message is echoed to the container's stdout.
- Running before `initialize()` raises a `ValueError`.
- The harness is an abstraction (`Harness`) with one implementation, `Claude`. A new CLI
  means a new subclass.

## Where
- `runner/harness/harness.py` — `Harness.run_task()`, `build_prompt()`
- `runner/harness/claude.py` — `Claude`
- Tests: `tests/harness/test_harness.py`
- Design: [`concept.md` §3.1, §4.1](../concept.md#31-the-run-lifecycle)
