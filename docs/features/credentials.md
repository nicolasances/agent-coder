# Credentials from Secret Manager

## What it does
Gives the agent the two credentials it needs, without ever putting one in the image or the
Task File.

## Behaviour
- At harness initialisation the runner fetches each secret the harness needs from GCP Secret
  Manager, in project `GCP_PID`, using the job's service account. Any failure to fetch aborts
  the run.
- `claude-token` — the Claude Code OAuth token, needed by the Claude harness.
- `coding-agent-gh-token` — the GitHub token, needed by every harness. It is passed to the
  agent process as `GH_TOKEN`, which `gh` reads natively.
- `GitOps.push_branch()` and `create_pull_request()` fetch the GitHub token lazily and never
  write it to `.git/config` or to disk.
- `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` come from the environment.

## Where
- `runner/gcp_secrets.py` — `get_secret()`
- `runner/harness/harness.py` — `Harness.initialize()`, `base_secrets`
- `runner/harness/claude.py` — `get_secrets_names()`
- `runner/git/gitops.py` — push and PR helpers
- Design: [`concept.md` §4.4](../concept.md#44-environment-variable-contract)
