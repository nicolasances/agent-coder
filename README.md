# Coding Agent

A containerised coding agent. It takes **one GitHub issue** and produces **one pull
request**, then exits.

It's part of a wider effort to automate the software development lifecycle (SDLC) through
agents: an external orchestrator hands this container a task, and the container clones the
target repository, runs an agent CLI (Claude Code today) against the working tree, commits,
pushes, opens a PR, and terminates. It holds no state between runs — the branch on GitHub
is the artifact.

For the full design and rationale behind these decisions, see
[`docs/concept.md`](docs/concept.md).

## Table of Contents

- [How it works](#how-it-works)
  - [The Task File](#the-task-file)
- [Running this locally](#running-this-locally)

## How it works

Given a task, the container:

1. Resolves the task (from a Task File in GCS)
2. Clones the repository
3. Runs the agent CLI against the working tree, with a fixed prompt: `/implement issue <issueURL>`
4. Exits

The agent in step 3 does the rest itself, through its skills: reads the issue, creates a
branch named after it, edits, commits, pushes, and opens the pull request. See
[`docs/concept.md` §3.1](docs/concept.md#31-the-run-lifecycle) for why the split falls
there.

### The Task File

The orchestrator writes one JSON object to
`gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json` before starting the container:

```json
{
    "taskId": "test-task-002",
    "repoURL": "https://github.com/nicolasances/agent-coder.git",
    "issueURL": "https://github.com/nicolasances/agent-coder/issues/3",
    "baseBranch": "main"
}
```

`taskId`, `repoURL` and `issueURL` are required; `baseBranch` defaults to `main`. There is
no free-form prompt field — a run is always the implementation of one specific issue.

## Running this locally

This obviously has to be run in a container.

So, first build it:
```bash
docker build . -t <your-image-tag>
```

Then run it:
```bash
 docker run --rm \
  -e GCP_PID="<your gcp project>" \    
  -e TASK_ID="<your task id>" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/home/agent/adc.json \
  -v "$HOME/<location of a valid GCP key json>:/home/agent/adc.json:ro" \
  nicolasances/agent-coder
```

e.g. 
```bash
 docker run --rm \
  -e GCP_PID="ASD" \    
  -e TASK_ID="test-task-001" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/home/agent/adc.json \
  -v "$HOME/dev/keys/toto-ms-llm-dev.json:/home/agent/adc.json:ro" \
  nicolasances/agent-coder
```
