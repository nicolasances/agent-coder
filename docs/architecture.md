# Architecture — Container, Dispatcher, and the Cloud Run Jobs Integration

> Status: architecture / decision document. Nothing here is implemented yet.
> Last revised: 2026-09-01.
> Scope: this document covers exactly three components — the containerized CLI (this
> repo), the Dispatcher API (a separate service), and the mechanism that connects them.
> Everything else that can *call* the Dispatcher (a web portal, an MCP server, a future
> GitHub webhook) is a client of it and is out of scope here. See
> [concept.md](concept.md) for the full system concept, the `TaskSpec` / `AgentEvent` /
> `RunResult` schemas, and the exit code taxonomy — this document does not redefine them,
> only says how they get used across the boundary.

## Table of Contents

1. [Component overview](#1-component-overview)
2. [The containerized CLI](#2-the-containerized-cli)
3. [The Dispatcher API](#3-the-dispatcher-api)
4. [Integration via the Cloud Run Jobs Admin API](#4-integration-via-the-cloud-run-jobs-admin-api)
5. [End-to-end sequence](#5-end-to-end-sequence)
6. [Not covered here](#6-not-covered-here)

---

## 1. Component overview

```
                    ┌─────────────────────────┐
  caller ──POST────►│   Dispatcher API         │  Cloud Run *service*
  (webapp, MCP,      │   (this doc, §3)         │  request-driven, scale-to-zero
   later: webhook)   └────────────┬─────────────┘
                                   │ Cloud Run Jobs
                                   │ Admin API (§4)
                                   ▼
                    ┌─────────────────────────┐
                    │   agent-coder container  │  Cloud Run *Job* execution
                    │   (this repo, §2)         │  one task, one PR, exits
                    └────────────┬─────────────┘
                                   │ AgentEvents, RunResult
                                   │ (HTTP EventSink)
                                   ▼
                    back to the Dispatcher API
```

Two independently deployable things, one narrow contract between them: a job execution
request going one way, an HTTP event stream coming back the other way. Neither component
needs to know how the other is built internally.

---

## 2. The containerized CLI

This is `agent-coder` — the harness defined in [concept.md](concept.md). Its role does not
change because a Dispatcher now exists; the Dispatcher is just one more thing that can
populate its environment variable contract. The point worth stating explicitly here is
what the container does **not** know:

- It does not know it is running as a Cloud Run Job. It does not call the Cloud Run API,
  read Cloud Run metadata, or behave differently on GCP versus a laptop.
- It does not know a Dispatcher exists, beyond the fact that `EVENT_SINK=http` and
  `EVENT_SINK_CONFIG` gave it a URL to POST events to. If those are unset, it degrades to
  stdout only — no code path in the container is Dispatcher-aware.
- It does not decide *when* to run, *what* task to run, or *whether* to retry. All three
  are the Dispatcher's job.

### Responsibilities (recap, scoped to this integration)

| Responsibility | Detail |
|---|---|
| Read input | `TaskSpec` from environment variables — the [§4.4 contract](concept.md#44-environment-variable-contract) in concept.md. The Dispatcher is one possible producer of these env vars; the container's parsing code has no idea which producer it was. |
| Run the lifecycle | clone → branch → skills → agent CLI → commit → push → PR → `RunResult` ([concept.md §3.1](concept.md#31-the-run-lifecycle)). |
| Emit observability | NDJSON `AgentEvent`s to stdout always, and to the configured `EventSink` (here: `http`, pointed at the Dispatcher — [concept.md §3.4](concept.md#34-observability--the-chatty-agent)). |
| Terminate | Exit with the code from the [taxonomy](concept.md#45-exit-code-taxonomy). This exit code is what Cloud Run Jobs itself surfaces as the execution's status — the Dispatcher does not need a separate side-channel to learn success/failure if it is also watching the terminal `AgentEvent`. |

Nothing here is new relative to `concept.md`. It is restated to make the boundary
explicit: **the container is a portable, Dispatcher-agnostic artifact.** Swapping the
Dispatcher for a manual `gcloud` command, or for GitHub Actions, requires zero changes to
this repo — only to what populates the env vars and where `EVENT_SINK_CONFIG` points.

---

## 3. The Dispatcher API

A small service, external to this repo, that turns "someone wants a task done" into "a
container is running against that task." It is the thing described as a possibility in
[concept.md §OQ-01](concept.md#7-open-questions): here it is a **custom REST API**, not
GitHub Actions and not a Temporal worker.

### Why a custom API

The callers are heterogeneous from the start — a web portal and an MCP integration talking
to Claude — and both need the same behavior: submit a task, get a run identifier back, and
observe progress. A single owned API gives one place to put auth, validation, and
idempotency instead of duplicating that logic per caller. It also gives the container
somewhere to POST its events, which a GitHub-Actions-only dispatcher would not.

### Responsibilities

| Responsibility | Detail |
|---|---|
| Accept a trigger | `POST /tasks` — repo, issue reference or free-form prompt, optionally overriding model/skills ref. |
| Build the `TaskSpec` | Derive what the caller didn't supply: `task_id` (idempotency key), `branch_name`, defaults for `base_branch`/`skills_ref`/`model`. |
| Launch the run | Call the **Cloud Run Jobs Admin API** (§4) with the `TaskSpec` fields as per-execution overrides. Does not shell out to `gcloud`; does not touch Pub/Sub or Eventarc — there is no queue to build here. |
| Receive progress | Accept `AgentEvent` POSTs from the running container (it is the container's `EVENT_SINK=http` target) and the terminal `RunResult`. |
| Expose status | `GET /tasks/{id}` for polling, or a stream, so a caller can watch a run without holding an open connection to the container itself. |
| Return promptly | `POST /tasks` responds `202` with a `run_id` immediately — a run takes minutes, far past any reasonable request timeout. It is not a synchronous call. |

### What it deliberately does not do

- **No git, no model calls, no push credentials.** `GITHUB_TOKEN` and `ANTHROPIC_API_KEY`
  are Secret Manager references configured statically on the Cloud Run Job resource, not
  values the Dispatcher ever reads or forwards. It only ever sends *task* fields, never
  secrets.
- **No retry/backoff engine.** One trigger, one execution — matching the container's own
  "one task, one PR" philosophy. If richer orchestration (retries, scheduling, fan-out)
  becomes necessary later, that is a reason to reconsider Temporal, not a reason to grow
  this API into one.
- **No knowledge of *why* a task was submitted.** Whether the caller was a human clicking a
  button or Claude calling an MCP tool is irrelevant past the auth boundary — one request
  shape in, one `TaskSpec` out.

### Hosting

Cloud Run **service** (distinct from the Cloud Run **Job** it launches): request-driven,
`min-instances=0`. It bills only while handling a request, which for personal-scale traffic
sits comfortably inside Cloud Run's always-free monthly request allotment. This keeps the
"$0 while idle" property from [concept.md §3.2](concept.md#32-two-tier-execution) intact
for the Dispatcher tier too, not just the agent tier.

---

## 4. Integration via the Cloud Run Jobs Admin API

This is the one mechanism connecting §2 and §3. It replaces both "shell out to `gcloud run
jobs execute`" (fine for a human, awkward for a service to invoke as a subprocess) and any
Pub/Sub/Eventarc indirection (unnecessary — the Dispatcher already knows exactly which job
to run and when).

### The call

The Dispatcher calls `RunJob` on the Jobs Admin API (`google.cloud.run_v2.JobsClient` in
the client libraries, or REST `POST .../jobs/{job}:run`), passing a `RunJobRequest` whose
`overrides.container_overrides[0].env` carries the per-run `TaskSpec` fields.

### Static on the Job resource vs. overridden per execution

| Static (set once, at deploy time) | Overridden per execution (set by the Dispatcher, per call) |
|---|---|
| Container image | `TASK_ID` |
| Service account | `REPO_URL` |
| Secret Manager references for `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` | `ISSUE_REF` or `TASK_PROMPT` |
| `ANTHROPIC_BASE_URL` (if routed through a gateway) | `BRANCH_NAME` |
| CPU / memory / timeout limits | `SKILLS_REF`, `MODEL` |
| | `EVENT_SINK=http`, `EVENT_SINK_CONFIG` (the Dispatcher's own callback URL + run id) |

This split is what keeps a secret from ever passing through the Dispatcher's request
handling: the Job resource already points at Secret Manager, and the Dispatcher's
overrides never mention a secret's value, only task data.

### IAM

The Dispatcher's service account needs only the ability to run *this specific job* —
`roles/run.developer` scoped to the job resource (via a condition or a narrower custom
role), not project-wide Cloud Run admin. The container, in turn, runs under its own service
account with access to exactly the two secrets it needs and nothing else. Two separate
identities, each minimal for its own side of the call.

### Correlating the execution

`RunJob` returns an execution name / operation. The Dispatcher stores this alongside its
own `task_id` so that later `AgentEvent`s arriving over HTTP (§3) — which carry `run_id` —
can be matched back to the request that started them.

---

## 5. End-to-end sequence

```
caller                Dispatcher API              Cloud Run Jobs API        container
  │  POST /tasks            │                             │                     │
  ├─────────────────────────►                             │                     │
  │                         │  build TaskSpec              │                     │
  │                         │  RunJob(overrides=TaskSpec)   │                     │
  │                         ├──────────────────────────────►                     │
  │  202 {run_id}           │                             │  starts execution    │
  ◄─────────────────────────┤                             ├─────────────────────►│
  │                         │                             │                     │  reads env,
  │                         │                             │                     │  runs lifecycle
  │                         │  AgentEvent (POST)            │                     │
  │                         ◄─────────────────────────────────────────────────────┤
  │  GET /tasks/{id}         │       ...repeats per event...                      │
  ├─────────────────────────►                             │                     │
  │  {status, latest event} │                             │                     │
  ◄─────────────────────────┤                             │                     │
  │                         │  RunResult / terminal event   │                     │
  │                         ◄─────────────────────────────────────────────────────┤
  │                         │                             │            exits (code N)
```

---

## 6. Not covered here

Intentionally out of scope for this document, either because they're already decided
elsewhere or genuinely undecided and not needed to describe these three components:

- **Callers of the Dispatcher** — the web portal, the MCP server/integration, and any
  future GitHub webhook are all just `POST /tasks` clients. Their own design lives
  elsewhere.
- **Auth model on the Dispatcher's API** — IAM identity tokens vs. a shared bearer token
  vs. something else depends on which caller is talking (a logged-in web user vs. a local
  MCP process). Open.
- **Run-state persistence** — whether the Dispatcher keeps run status in memory, Firestore,
  or elsewhere is an implementation detail of §3, not part of the container/Job/API
  contract itself.
- **Everything already decided in `concept.md`** — the `TaskSpec`, `AgentEvent`, and
  `RunResult` schemas, the exit code taxonomy, the skills-pinning decision, and the
  Cloud Run Job vs. GKE choice for the agent tier itself.
