# Coding Agent

A containerised coding agent. It takes **one GitHub issue** and produces **one pull
request**, then exits.

It's part of a wider effort to automate the software development lifecycle (SDLC) through
agents: an external orchestrator hands this container a task, and the container clones the
target repository, runs an agent CLI (Claude Code today) against the working tree, commits,
pushes, opens a PR, and terminates. It holds no state between runs — the branch on GitHub
is the artifact.

For the full design and rationale behind these decisions, see
[`docs/concept.md`](docs/concept.md). For what the service does, feature by feature, see
[`docs/features/`](docs/features/README.md).

## Table of Contents

- [How it works](#how-it-works)
  - [Runtime: GKE, KEDA and Pub/Sub](#runtime-gke-keda-and-pubsub)
  - [The Task File](#the-task-file)
  - [Configuration](#configuration)
  - [Ack/nack policy](#acknack-policy)
  - [Timeouts](#timeouts)
  - [Triggering a run](#triggering-a-run)
- [Running this locally](#running-this-locally)

## How it works

Given a task, the container:

1. Pulls one task from Pub/Sub (or takes `TASK_ID` from the environment, in local mode)
2. Installs the latest coding skills from `nicolasances/skills-coding`
3. Resolves the task (from a Task File in GCS)
4. Skips the run if an open PR for the issue already exists
5. Clones the repository
6. Runs the agent CLI against the working tree, with a fixed prompt: `/implement issue <issueURL>`
7. Acks or nacks the message by outcome, and exits with the matching exit code

The agent in step 6 does the rest itself, through its skills: reads the issue, creates a
branch named after it, edits, commits, pushes, and opens the pull request. See
[`docs/concept.md` §3.1](docs/concept.md#31-the-run-lifecycle) for why the split falls
there.

### Runtime: GKE, KEDA and Pub/Sub

The container runs as a pod of a KEDA `ScaledJob` (`agent-coder`, namespace `agents-dev`),
which starts pods from the backlog of a Pub/Sub subscription. KEDA does **not** hand the
message to the pod: the pod pulls its own task, with a synchronous pull of exactly one
message. If the pull is empty (KEDA started a pod but there is nothing left), the pod logs
it and exits `0`.

The message body is the task id:

```json
{ "taskId": "test-task-002" }
```

The task id names the Task File below. The infrastructure (topic, subscription with
exactly-once delivery and a dead-letter topic, KEDA, IAM) lives in `toto-terra-gke` and
`toto-terra`, not here.

Because a run can last hours and Pub/Sub's maximum ack deadline is 600s, a background
thread extends the lease (`modify_ack_deadline(600)`) every 5 minutes until the run ends.
Failed acks and lease extensions are logged, never fatal.

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

### Configuration

| Variable | Required | Notes |
|---|---|---|
| `GCP_PID` | yes | GCP project holding the `{GCP_PID}-agents-data` bucket and the Secret Manager secrets. |
| `PUBSUB_PROJECT_ID` | queue mode | GCP project of the Pub/Sub subscription (the GKE project; not necessarily `GCP_PID`). |
| `PUBSUB_SUBSCRIPTION` | queue mode | Subscription to pull the task from. |
| `TASK_ID` | local mode | If set, Pub/Sub is skipped entirely and this task id is run. |
| `TASK_TIMEOUT_SECONDS` | no | Internal run timeout. Default `10800` (3 hours). |

### Ack/nack policy

| Outcome | Exit code | Pub/Sub |
|---|---|---|
| PR opened | `0` | ack |
| Open PR for the issue already exists (duplicate delivery) | `0` | ack, agent not run |
| No change needed | `10` | ack |
| Task failed | `20` | ack |
| Validation failed | `21` | ack |
| Infra failure (GCS, Secret Manager, clone, push, ...) | `30` | **nack** (redelivered) |
| Timeout | `40` | ack |
| Crash / OOM / eviction | n/a | lease expires, redelivered |
| SIGTERM | `143` | **nack immediately**, agent stopped |

Redelivery is capped by the subscription's dead-letter policy. A non-zero exit code from
the agent CLI that is not in this table is treated as `20`: the CLI does not let us tell
"could not solve it" from "model unreachable", and retrying a long run is the expensive
mistake. A message that is not `{"taskId": "..."}` is acked and dropped.

A duplicate is detected by looking for an open PR in the task's repo that closes the
issue (a `Closes #N`-style keyword in the PR body, as the `/implement` flow writes it).
A pushed branch with no PR is ignored and the run goes ahead normally.

### Timeouts

There are two layers. `TASK_TIMEOUT_SECONDS` (3h) is the real bound: on expiry the agent
is stopped, the run exits `40` and the message is acked. Kubernetes' `activeDeadlineSeconds`
(3h15m) is only a backstop: if it fires, the lease expires and the message is retried, up to
the dead-letter limit.

### Triggering a run

Write the Task File to GCS, then publish the task id:

```bash
gcloud pubsub topics publish agent-coder-tasks-dev --message '{"taskId":"test-task-002"}'
```

## Running this locally

This obviously has to be run in a container.

So, first build it:
```bash
docker build . -t <your-image-tag>
```

Then run it. Setting `TASK_ID` skips Pub/Sub, so no orchestrator or queue is needed:
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
