# Coding Agent

A containerised coding agent. It takes **one task** — typically a GitHub issue — and
produces **one pull request**, then exits.

It's part of a wider effort to automate the software development lifecycle (SDLC) through
agents: an external orchestrator hands this container a task, and the container clones the
target repository, runs an agent CLI (Claude Code today) against the working tree, commits,
pushes, opens a PR, and terminates. It holds no state between runs — the branch on GitHub
is the artifact.

For the full design and rationale behind these decisions, see
[`docs/concept.md`](docs/concept.md).

## Table of Contents

- [How it works](#how-it-works)
- [Running this locally](#running-this-locally)

## How it works

Given a task, the container:

1. Resolves the task (from a Task File in GCS)
2. Clones the repository
3. Checks out a new branch
4. Runs the agent CLI against the working tree
5. Commits and pushes the changes
6. Opens a pull request
7. Exits

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
