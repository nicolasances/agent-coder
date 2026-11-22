# Repository clone

## What it does
Puts the target repository's working tree at `/workspace` so the agent has something to work on.

## Behaviour
- Runs `git clone --branch <baseBranch> <repoURL> /workspace`.
- A non-zero exit raises a `RuntimeError`.
- On success the clone path is exposed as `GitOps.local_path` and becomes the agent's working
  directory.
- The runner does not branch, commit, push or open the PR. The agent does that through its
  skills ([`concept.md` §3.1](../concept.md#31-the-run-lifecycle)). `GitOps` also has
  `push_branch()` and `create_pull_request()` helpers, which `main()` does not currently call.

## Where
- `runner/git/gitops.py` — `GitOps.clone_repo()`
- Tests: `tests/git/test_gitops.py`
