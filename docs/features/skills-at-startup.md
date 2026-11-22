# Skills at startup

## What it does
Installs the coding skills (`prepare`, `implement`, `code`, ...) that tell the agent how to
work, from `nicolasances/skills-coding`, at the start of every run.

## Behaviour
- Runs `npx skills add nicolasances/skills-coding --global -y` as the first step of `main()`,
  before the harness is loaded or the task is resolved.
- Always takes the repo's default branch (`main`), so a change pushed to the skills repo
  reaches the next run without rebuilding the image.
- `--global` makes the skills apply to whichever repo is cloned into `/workspace`. The install
  runs as the `agent` user, so it lands in `/home/agent`.
- The repo is public: no credentials, only outbound access to GitHub.
- If the install fails (non-zero exit, or `npx` missing), the run exits with code `30`
  (infra failure, retryable). The agent is never started without skills, and there is no
  baked-in fallback copy.
- The resolved commit is not recorded. Runs are not reproducible with respect to skills.

## Where
- `runner/skills.py` — `install_skills()`, `SkillsInstallError`
- `runner/main.py` — calls it first, maps the error to exit code 30
- `Dockerfile` — installs only the `skills` CLI, not the skills themselves
- Tests: `tests/skills/test_skills.py`, `tests/test_main.py`
- Design: [`concept.md` §3.5](../concept.md#35-skills--pinned-not-latest), issue #10

## Out of scope
Pinning to a ref or SHA, recording `skills_sha`, private skills repos.
