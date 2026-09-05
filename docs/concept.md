# Coding Agent — Concept

> Status: concept / decision document. Parts of it are now implemented — see
> [Appendix A](#appendix-a--current-repo-state-vs-target) for exactly which.
> Last revised: 2026-09-03. Task input/output moved from environment variables to
> GCS-backed JSON files (§3.3, §4.4, §6.1, §8); `TaskSpec` cut to four fields, with
> skills, harness, model, event sink and per-task timeout deferred rather than built
> (§3.5, §3.6, §4.1, §4.4, §8, §9); Task File JSON keys are camelCase and the bucket is
> derived from `GCP_PID` rather than a separate `TASK_BUCKET` variable (§4.1, §4.4); a
> raw `trace.json` capture of stdout was added as a stopgap ahead of the real
> `AgentEvent`/`EventSink` design (§3.4).

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Core Concepts](#2-core-concepts)
3. [Features](#3-features)
4. [Data Models](#4-data-models)
5. [Key User Stories](#5-key-user-stories)
6. [Constraints & Assumptions](#6-constraints--assumptions)
7. [Open Questions](#7-open-questions)
8. [Not Doing (and Why)](#8-not-doing-and-why)
9. [Ideas for Future Versions](#9-ideas-for-future-versions)
- [Appendix A — Current repo state vs. target](#appendix-a--current-repo-state-vs-target)

---

## 1. Purpose & Scope

### 1.1 What is this?

A containerised coding agent. 
It takes **one task**, produces **one pull request**, and exits.

An external orchestrator starts a container and hands it a task — typically a GitHub issue. 
The container 
- clones the repository, 
- creates a branch, 
- fetches a pinned set of skills, 
- runs an agent CLI (Claude Code today) against the working tree, 
- commits, pushes, 
- opens a PR, and terminates. 

It holds no state between runs. The branch on GitHub is the artifact.

The agent CLI is not the product. Anyone can wrap `claude -p` in a Dockerfile in anafternoon. What this repository owns is the **contract** around that CLI: a defined input, a defined output, a defined event stream, a defined failure taxonomy, and a packaged workflow — such that the same thing runs unchanged in two very different clouds.

### 1.2 Who is it for?

This repo is part of a wider attempt to automate the SDLC through Agents.

It should work in different contexts: 

- **Personal.** Personal GCP project. Must cost approximately nothing when idle. Optimised for cheapness and for the ability to iterate quickly. This should be used by users with personal subscriptions to Agent harnesses (e.g. Claude) and that want to automate their SDLC without incurring huge costs. 

- **Professions.** Company platform, GKE-based, deployed through the platform's own pipeline. Optimised for fitting in with existing conventions.

### 1.3 What problems does it solve?

- **SDLC Agentic Automation**: this is part of an automated SDLC process. 
- **Two environments, one behaviour.** Without an explicit contract, the personal and professional setups will diverge into two codebases that happen to share a name.
- **Runtime undecided.** Cloud Run versus GKE is an open question.
- **Non-reproducible agent behaviour.** An agent whose instructions can silently change
  between runs cannot be debugged after the fact.

### 1.4 Out of scope (v1)

- **The orchestrator itself.** It lives elsewhere. This repository is the agent tier only.
- **Human-in-the-loop mid-run.** A run is bounded and unattended. PR review feedback starts a *new* run.
- **Resumable sessions.** A run that dies is retried from the beginning, not resumed.
- **Fan-out.** One task, one container, one PR.
- **Multi-tenancy.** This is one person's tool, not a platform capability other teams point at their repositories.

---

## 2. Core Concepts

| Term | Definition |
|---|---|
| **Harness** | This repository. The containerised agent tier: one task in, one PR out. |
| **Adapter** | An implementation of the `Harness` protocol for a specific agent CLI (Claude Code, Codex, Gemini CLI). Knows how to launch that CLI *and* how to read its output. |
| **Task** | A unit of work small enough for one unattended run. Usually a GitHub issue. |
| **Run** | One execution of the container against one task. Has an id, a start, an end, an exit code, and a result. |
| **Orchestrator** | Whatever decides that a task should run, launches it, and records what happened. Temporal at work; undecided at home. **Not in this repository.** |
| **Dispatcher** | The always-on process that polls the orchestrator for work and launches agent containers. Part of the orchestrator tier, not the harness. |
| **Skill Pack** | The versioned set of skills, prompts and workflows that tell the agent *how* to work — as distinct from *what* to work on. |
| **Skills Ref** | The git ref (tag, branch or SHA) identifying which version of the Skill Pack a run used. |
| **Agent Event** | One structured, versioned observation emitted during a run. The unit of observability. |
| **Event Sink** | Where Agent Events are sent. A plugin: stdout, Temporal, HTTP, or nothing. |
| **Run Result** | The structured summary a run emits on completion — status, branch, PR URL, skills SHA, token usage. |
| **Task File** | `task.json` in GCS, holding one `TaskSpec`. Written once by the dispatcher, immutable — the audit record of what was asked. |
| **Result File** | `task-output.json` in GCS, holding one `RunResult`. Written by the container at termination — the audit record of what happened. |
| **Trace File** | `trace.json` in GCS — every raw stdout line from the harness subprocess, parsed where possible. A debugging aid for one run, not the versioned `AgentEvent` stream (§3.4, §4.2); see the v1 note at the end of §3.4. |

---

## 3. Features

### 3.1 The run lifecycle

The container performs a fixed sequence of phases. Naming them is the point: today `runner/main.py` implements none of them — it builds a command, streams output, and stops.

```
resolve task
  → clone repo
  → checkout new branch
  → resolve + fetch Skill Pack
  → run agent CLI
  → commit
  → push branch
  → open PR
  → emit Run Result
  → exit
```

Every phase emits at least one Agent Event, so a stalled run is diagnosable to the phase.

**Design decision — the runner owns the git operations, not the agent.** The alternative is to tell the agent, in its prompt, to commit and push and open a PR itself. That is tempting because it is less code. It is rejected for three reasons:

1. **Determinism.** Branch naming, commit trailers and PR body formatting become code
   with tests, not prose the model may reinterpret.

2. **Credential blast radius.** If the runner performs the push, the push credential never
   needs to be reachable by the agent's shell. The agent edits files; it does not publish.

3. **Failure attribution.** "The agent could not solve the task" and "the push was
   rejected" are different outcomes with different retry semantics. Merging them into one
   opaque agent turn destroys that distinction.

**Branch naming, specifically (revised 2026-09-03):** the dispatcher no longer supplies
`branch_name` — see [§4.1](#41-taskspec--the-input). The harness derives it itself from the
task's `prompt`, once the container has it. That still satisfies the determinism argument
above only if the derivation is itself deterministic code, not a free-form model turn;
whether it's a plain slug of the prompt or a small, separately-controlled summarisation
call is open — see OQ-11.

This remains an open question only in its details (see OQ-05), not in its direction.

### 3.2 Two-tier execution

The orchestrator was chosen as Temporal. 

**The collision.** A Temporal worker *polls* a task queue. Temporal Cloud cannot push work
to you; something must be awake to pull it. Polling means a process is always running.
"The container is a Temporal worker" and "I pay nothing when idle" cannot both be true.

**The resolution.** Two different things want to run, with wildly different cost profiles:

- **Orchestration logic** — decide, retry, time out, record. Tiny. Milliseconds of CPU.
  Must be awake to poll.
- **The coding agent** — clone, reason, edit, push. Minutes to tens of minutes, and the
  only thing that costs real money.

Make the cheap thing always-on and the expensive thing scale-to-zero:

```
GitHub issue labelled "agent"
        │
        ▼
┌────────────────────────────┐
│ Temporal Cloud             │  run record · retries · timeouts · history
└───────────┬────────────────┘
            │ polled by
┌───────────▼────────────────┐
│ Dispatcher worker          │  always-on, tiny, cheap
│                            │  NOT this repo
└───────────┬────────────────┘
            │ launches one execution
┌───────────▼────────────────┐
│ agent-coder container      │  THIS REPO
│  clone → skills → agent    │  one task, then exits
│  → commit → push → PR      │  scale-to-zero by construction
└───────────┬────────────────┘
            │ progress events
            └───────────────────► back to Temporal
```

This is also what draws the repository boundary. **The dispatcher is the orchestrator and
does not live here.** This repository is one thing: a container that turns a task into a
PR. That boundary is what lets the orchestrator be Temporal at DR and possibly something
much dumber at home, without the harness noticing.

**Runtime mapping:**

| | Home | DR |
|---|---|---|
| Agent tier | Cloud Run Job, one execution per task | Kubernetes Job (see OQ-02) |
| Dispatcher tier | Undecided (see OQ-01) | Long-running workload on GKE |
| Image build | Personal pipeline → Artifact Registry | DR platform pipeline → DR registry |

**Compute cost is noise, and the doc should be explicit about it.** A run is mostly
latency waiting on the model — low CPU utilisation for 5–30 minutes. The tokens consumed
by that run cost orders of magnitude more than the vCPU-minutes. Scale-to-zero therefore
matters as *"I refuse to pay for an idle node pool"*, **not** as *"per-run compute must be
minimised"*. Optimising the runtime for compute price is optimising the wrong axis, and
several otherwise-attractive designs die on this point for no good reason.

### 3.3 Portability as a contract, not as an artifact

Portability here means **the same contract**, not the same image bytes. Two builds of the
same Dockerfile, from two different pipelines, into two different registries, is expected
and acceptable — DR's platform will want to build through its own path, and fighting that
buys nothing.

What the container needs from any platform is short enough to enumerate:

1. Outbound network — to GitHub, to the model endpoint, and to GCS.
2. An ephemeral writable disk for `/workspace`.
3. Secrets injected as environment variables at execution time.
4. Read/write access to one GCS bucket, for the Task File and the Result File.

That is the entire list. No volumes, no PVCs, no service mesh, no ingress. **Git remains
the only I/O channel for code** — clone in, PR out; nothing about that changed. GCS carries
a different thing: the *task record*, not code — what was asked (input) and what happened
(result), each written once, keyed by `task_id` and `run_id` respectively. Neither object
is ever updated in place by more than one writer, so this does not reintroduce shared
mutable state between runs — it is an audit trail, not a database. *(Revised 2026-09-03 —
see [§6.1](#61-constraints) and [§8](#8-not-doing-and-why) for the earlier, now-superseded,
git-only-I/O constraint this replaces.)* The choice between Cloud Run Jobs and Kubernetes
Jobs remains close to a non-decision — both read and write a GCS object with no more
effort than they read an env var.

The portable interface is therefore three things, all specified in [§4](#4-data-models):

- a single **`TASK_ID` execution override, resolved against GCS** (input),
- the **exit code taxonomy** (outcome),
- the **stdout NDJSON event stream, plus the GCS Result File** (observation).

Anything that cannot be expressed in those three is environment-specific and belongs in
the orchestrator, not here.

### 3.4 Observability — the chatty agent

The harness is deliberately *not* a dumb pipe. It reports what it is doing. But it must do
so without becoming dependent on any one orchestrator, or portability dies immediately.

The resolution is to separate **vocabulary** from **transport**:

```
raw CLI line → Harness.parse() → AgentEvent → EventSink.emit()
```

- The **event vocabulary is the contract**, and it is versioned. See
  [§4.2](#42-agentevent).
- The **transport is a plugin**: `stdout` | `temporal` | `http` | `none`.

Stdout NDJSON is *always* on, regardless of which sink is configured. That single decision
means the container runs on a laptop, with `EVENT_SINK=none`, with no orchestrator
anywhere, and still produces a full trace. Local reproduction of a production run stays
possible.

This also fixes a real defect in the current code. `Harness` today has only
`build_command()` — it abstracts *launching* a CLI but not *reading* one, so
`runner/main.py` parses Claude Code's `stream-json` shape inline. `parse()` is the missing
half of that protocol, and its output is precisely what the sink consumes. See
[Appendix A](#appendix-a--current-repo-state-vs-target).

**For the Temporal sink specifically**, the pattern to evaluate is Temporal's
*async activity completion*: the launching activity passes the container an activity task
token, and the container heartbeats progress and completes the activity itself. That is
Temporal's canonical answer for long-running work executed outside a worker, and it would
make progress reporting fall out of the design rather than being bolted onto it.

> **Verify before building.** The existence of this pattern is asserted here; the current
> API shape, method names and heartbeat payload limits are **not**. Check Temporal's
> primary documentation before committing to it.

**v1 implementation note (2026-09-03) — the Trace File is not the event stream above.**
`Harness.run_command()` collects every raw stdout line (parsed as JSON where possible,
kept verbatim otherwise) and, once the subprocess exits, uploads the whole array as
`trace.json` next to the Task File — best-effort; a failed upload is logged, never
fatal. This is deliberately the plain thing, not `parse()` → `AgentEvent` → `EventSink`:
no vocabulary, no versioning, no typed events, just "what did the CLI actually print
during this run." It exists because that design doesn't yet, and a raw capture is more
useful than nothing while it's missing. It is not a stepping stone that has to be
migrated later — the two can coexist: `AgentEvent`/`EventSink`, if and when built, is the
structured, real-time channel; `trace.json` stays the cheap, unstructured, after-the-fact
one. Keyed by `task_id` like the Result File, so it inherits the same retry-overwrite
question — see OQ-12.

### 3.5 Skills — pinned, not latest

The Skill Pack tells the agent *how* to work. Three ways to get it into a run:

| | Baked into image | Latest at startup | **Pinned ref at startup** |
|---|---|---|---|
| Reproducible | Yes | **No** | Yes |
| Change without rebuild | No | Yes | Yes |
| Startup failure mode | None | Network + auth | Network + auth |
| Roll back skills alone | No | No | Yes |
| Home and DR can differ | Only by rebuilding | No | Yes, via config |
| Change is reviewable | Yes (image build) | **No** | Yes (release) |

**Decision: pinned ref, resolved by the orchestrator.** *(Deferred for v1 — see the note at
the end of this section. The reasoning below stays valid for when this comes back.)*

The case against `latest` is not convenience, it is forensics and safety:

- **Forensics.** When a run does something stupid, the first question is "what was it
  told?" With `latest`, that question is unanswerable — the skills moved. The same image,
  the same input and the same task can produce different behaviour on different days, with
  nothing in the record explaining why.
- **Safety.** Anyone who can push to the Skill Pack repository silently changes agent
  behaviour in every environment, DR included, with no review gate. That is a production
  deploy without a deploy.

**How it works.** The orchestrator decides `SKILLS_REF` and it lands in the workflow
history. The container fetches that ref and records the **resolved commit SHA** — not just
the tag — in the Run Result. Tags move; SHAs do not. "Which skills ran?" becomes
answerable forever, for every run.

This gives up nothing that "download at startup" was wanted for. Skills still change
without an image rebuild. Skills still roll back independently of the image. And home can
set `SKILLS_REF=main` for fast iteration while DR pins a release — *same image, same
contract, different config*, which is exactly the principle in [§3.3](#33-portability-as-a-contract-not-as-an-artifact).

**Fallback.** If Skill Pack egress or credentials turn out to be awkward at DR, baking the
pack into the image is the documented retreat. It is more rigid, not wrong. What is
rejected outright is fetching an unpinned `latest`.

**v1 (revised 2026-09-03): the fallback is the starting point.** Skills are baked into the
image — the "Baked into image" column above, not "Pinned ref at startup." There is no
Skill Pack repo yet, and no second environment yet to justify runtime selection.
`skills_ref` is removed from the Task File accordingly ([§4.1](#41-taskspec--the-input),
[§4.4](#44-environment-variable-contract)); `SKILLS_REPO_URL` is removed too, since there
is nothing to fetch. This is a deferral, not a reversal of the argument above: the day a
real Skill Pack exists and needs to roll back independently of the image, the pinned-ref
design in this section is what to build, unchanged.

### 3.6 Extension seams

Exactly two, for v1:

| Seam | Varies | Implementations |
|---|---|---|
| `Harness` | Which agent CLI | Claude Code (v1). Codex, Gemini CLI later. |
| `EventSink` | Where events go | `stdout` (always), `temporal`, `http`, `none`. |

**v1 note (2026-09-03):** only the `stdout` `EventSink` exists in code. The seam stays
named here because it costs nothing to leave open, but nothing in the Task File selects a
sink — see [§4.1](#41-taskspec--the-input), [§8](#8-not-doing-and-why).

**There is deliberately no git-host seam.** Both setups are GitHub cloud, so clone,
branch, push and PR are one code path with no abstraction over them. If DR ever moves to
GitHub Enterprise Server, a configurable API base URL covers it. A move to Azure DevOps or
Bitbucket would make a third seam necessary — that is the single change most likely to
force this design open.

Resisting a premature third abstraction here is intentional. Two seams that earn their
keep beat three that anticipate a future that may not arrive.

---

## 4. Data Models

### 4.1 `TaskSpec` — the input

Supplied by the orchestrator as a JSON object written to GCS — the **Task File** — and
resolved by the container from a single `TASK_ID` execution override (see
[§4.4](#44-environment-variable-contract)). The dispatcher writes the Task File *before*
triggering the execution, so `TASK_ID` always resolves once the container starts.

**Layout (implemented 2026-09-03, `runner/main.py`):** the bucket holds one task per
agent, not just per harness — `gs://{bucket}/{agent_name}/{task_id}/task.json`.
`agent_name` is `coder`, hardcoded (it names this repo, not a per-deployment choice),
which is what makes the bucket shareable across other agents later without a naming
collision. The bucket itself is **not** a separate `TASK_BUCKET` variable — it's derived
as `{GCP_PID}-agents-data`, reusing the project id already needed for Secret Manager
(§4.4). One fewer variable to keep in sync, at the cost of a fixed naming convention the
bucket itself must follow.

**Wire format note:** the Task File's JSON keys are camelCase (`taskId`, `repoURL`,
`baseBranch`) — the table below uses the `TaskSpec` class's own (snake_case) attribute
names, which is what `TaskSpec.from_json()` maps them to.

**(Revised 2026-09-03 — cut to four fields.)** `issue_ref`, `branch_name`, `skills_ref`,
`harness`, `model`, `event_sink`, `event_sink_config` and `timeout_seconds` are all gone
from this table. None were wrong in principle; each was configurability for a choice this
project doesn't have to make yet — one harness, one model, one sink, no separate issue
format, no Skill Pack repo. See [§8](#8-not-doing-and-why) for the field-by-field reasoning
and [§9](#9-ideas-for-future-versions) for when each comes back.

| Field | Type | Notes |
|---|---|---|
| `task_id` | string | Stable id from the orchestrator. Idempotency key, and must match the Task File's folder name (`coder/{task_id}/task.json`). |
| `repo_url` | string | HTTPS clone URL. |
| `prompt` | string | The task, in the orchestrator's own words. May reference an issue, a doc, anything — no format is enforced. |
| `base_branch` | string | Default `main`. |

`branch_name` is no longer supplied here — the harness derives it from `prompt` once the
run is underway. See [§3.1](#31-the-run-lifecycle) and OQ-11.

### 4.2 `AgentEvent`

```json
{
  "schema_version": 1,
  "run_id": "…",
  "seq": 42,
  "ts": "2026-08-31T09:58:00Z",
  "type": "tool.used",
  "payload": { }
}
```

`seq` is monotonic per run so a consumer can detect gaps and reorder.

**v1 event types:**

| Type | Emitted when |
|---|---|
| `run.started` | Container has parsed its TaskSpec. |
| `repo.cloned` | Clone succeeded; carries base commit SHA. |
| `skills.resolved` | Skill Pack fetched; **carries the resolved commit SHA**. |
| `agent.thinking` | Agent reasoning text. |
| `agent.message` | Agent assistant text. |
| `tool.used` | Agent invoked a tool. |
| `commit.created` | Runner committed; carries SHA. |
| `pr.opened` | PR created; carries URL. |
| `run.succeeded` | Terminal, success. |
| `run.failed` | Terminal, failure; carries the exit code and reason. |

### 4.3 `RunResult` — the output

Written to GCS as the **Result File** — `gs://{bucket}/coder/{task_id}/task-output.json`,
next to the Task File it answers — and emitted on the event stream at termination. `/out`
is removed; see [Appendix A](#appendix-a--current-repo-state-vs-target). Not yet
implemented — the Task File read and the Trace File write both exist (`runner/main.py`,
§3.4), but `RunResult` itself does not yet.

**(Revised 2026-09-03 — keyed by `task_id`, not `run_id`.)** The earlier version of this
section keyed the Result File by `run_id` specifically so a retried task wouldn't clobber
its previous attempt's result. One file per task folder gives up that property: a retry
overwrites `task-output.json`. Recorded honestly rather than re-argued away — see OQ-12.

| Field | Type |
|---|---|
| `run_id`, `task_id` | string |
| `status` | `succeeded` \| `no_change` \| `task_failed` \| `infra_failed` |
| `branch` | string \| null |
| `pr_url` | string \| null |
| `commit_shas` | string[] |
| `base_sha` | string |
| `skills_sha` | string — resolved, not the ref |
| `harness`, `model` | string |
| `token_usage` | object |
| `duration_seconds` | int |
| `exit_code` | int |
| `error` | object \| null |

`skills_sha` plus `base_sha` plus the image tag is the full reproduction triple. Any run
can be re-created exactly from those three values.

### 4.4 Environment variable contract

**(Revised 2026-09-03.)** Per-task fields no longer travel as individual environment
variables — they live in the Task File ([§4.1](#41-taskspec--the-input)), a JSON object in
GCS. What crosses the environment-variable boundary now splits into two kinds, and the
distinction is the point: **deployment-level** variables are set once, when the Cloud Run
Job resource itself is configured, and are identical for every execution; **per-execution**
variables are set by the dispatcher's run-with-overrides call, and are what actually varies
from task to task. Collapsing that distinction was the flaw in the previous version of this
table — it made every field look like it needed a fresh decision on every dispatch, when
almost none of them do.

**Per-execution override — one variable:**

| Variable | Required | Notes |
|---|---|---|
| `TASK_ID` | yes | Names the Task File: `gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json`. The only thing that changes between runs. |

**Deployment-level — set once per environment:**

| Variable | Required | Notes |
|---|---|---|
| `GCP_PID` | yes | GCP project id. Used both for Secret Manager (as before) and to derive the bucket — `{GCP_PID}-agents-data` — holding Task Files, Result Files and Trace Files, one folder per agent (`coder/…`), shared with other agents. *(Revised 2026-09-03 — supersedes the `TASK_BUCKET` variable this section originally specified; see §4.1.)* |
| `ANTHROPIC_API_KEY` | yes | secret, injected at execution |
| `ANTHROPIC_BASE_URL` | no | set when routing via an internal gateway |

**`GITHUB_TOKEN` reconciled (implemented 2026-09-03, issue #1) — removed from the table
above.** It was listed here as a raw deployment-level env var, which never matched how
`claude-token` actually works, and nothing implemented either path. The mechanism now
mirrors `claude-token` exactly: a GCP Secret Manager secret named `github-token`, fetched
via the same `runner/gcp_secrets.get_secret()` helper — but by `GitOps`, not `Harness`,
since git/GitHub credentials are a different concern from the LLM CLI's own. It's fetched
lazily, at the point `push_branch()` or `create_pull_request()` needs it, not once at
startup, and it never becomes a literal `GITHUB_TOKEN` variable in this container's own
environment: `push_branch()` uses it as a one-off authenticated push URL (never written
to `.git/config`), and `create_pull_request()` passes it as `GH_TOKEN` in the `gh`
subprocess's environment specifically, which `gh` reads natively.

`SKILLS_REPO_URL` is removed *(2026-09-03)* — v1 bakes skills into the image, so there is
nothing to fetch. See [§3.5](#35-skills--pinned-not-latest).

**Task File fields (in GCS, not the environment; JSON keys are camelCase — see the wire
format note in §4.1):**

| Field (JSON key) | Required | Notes |
|---|---|---|
| `task_id` (`taskId`) | yes | Must match the object name. Idempotency key. |
| `repo_url` (`repoURL`) | yes | *(Not currently enforced by `TaskSpec.from_dict()`'s validation — see Appendix A.)* |
| `prompt` | yes | |
| `base_branch` (`baseBranch`) | no | default `main` |

No credential is ever baked into the image, and no credential is ever written into a Task
File — secrets stay exclusively in environment variables injected from Secret Manager at
execution time. This is already true of the current Dockerfile and must stay true.

### 4.5 Exit code taxonomy

This is load-bearing, not cosmetic: **a Temporal retry policy keys off it**, so it belongs
in the contract rather than in the implementation. The critical distinction is between
failures that are worth retrying and failures that are not.

| Code | Meaning | Retry? |
|---|---|---|
| `0` | PR opened. | No |
| `10` | No change needed — agent concluded correctly that nothing was required. | No |
| `20` | Task failed — the agent could not solve it. | **No.** Retrying wastes tokens to reach the same conclusion. |
| `21` | Validation failed — changes were produced but did not pass checks. | No, in v1 |
| `30` | Infra failure — clone failed, model unreachable, push rejected, skills fetch failed. | **Yes** |
| `40` | Timeout. | Orchestrator's judgement |

Collapsing `20` and `30` into a single non-zero code is the mistake this table exists to
prevent. They demand opposite responses.

---

## 5. Key User Stories

| # | As a user, I want to… | So that… |
|---|---|---|
| US-01 | label a GitHub issue and later find a PR | I can delegate a bounded task and review the result on my own schedule |
| US-02 | watch a run's progress while it happens | a stalled or looping run is visible before it burns an hour of tokens |
| US-03 | see exactly which skills, base commit and image a past run used | I can reproduce and debug a run weeks later |
| US-04 | run the container on my laptop with no orchestrator | I can develop and debug the harness without cloud infrastructure |
| US-05 | cancel a runaway run | a misbehaving agent has a bounded cost |
| US-06 | change or roll back skills without rebuilding the image | iterating on how the agent works is cheap and reversible |
| US-07 | tell "the agent failed" apart from "the infrastructure failed" | retries happen when they can help and not when they cannot |
| US-08 | run the same harness at home and at DR | one codebase, two deployments |

---

## 6. Constraints & Assumptions

### 6.1 Constraints

- **Scale to zero at home.** No standing node pool in the personal GCP project. Applies
  to the agent tier absolutely; the dispatcher tier is the compromise, and is unresolved
  (OQ-01).
- **Contract-level portability.** Same env vars, same exit codes, same event stream.
  *Not* the same image bytes — two builds from two pipelines is expected.
- **Git-only I/O for code.** Clone in, push out — no volumes, no shared mutable state
  between runs. *(Revised 2026-09-03 — no longer "no object store.")* GCS now carries the
  Task File and Result File as write-once, immutable objects keyed by `task_id` / `run_id`;
  see [§3.3](#33-portability-as-a-contract-not-as-an-artifact),
  [§4.4](#44-environment-variable-contract), [§8](#8-not-doing-and-why). That is a
  deliberately narrow exception: one object-store dependency, used only for append-only
  audit records, never for code or workspace state. It still keeps the runtime decision
  cheap — both Cloud Run Jobs and Kubernetes Jobs read and write a GCS object with no more
  effort than they read an env var.
- **GitHub cloud on both sides.** Confirmed. One code path.
- **DR platform conventions.** Whatever the platform requires for deployment to GKE.
  Currently unread — see [§6.3](#63-a-note-on-the-dr-platform-docs).

### 6.2 Assumptions — stated as bets

Each of these is something believed but not verified. Each names what would invalidate it.

**A-01 — Model egress is permitted at DR, or a gateway exists.**
The `ANTHROPIC_BASE_URL` comment already in the Dockerfile suggests the gateway case was
anticipated. *Related and easy to miss:* a container cannot authenticate with a personal
Claude subscription — it requires an API key or a gateway credential. **Whose billing
applies at DR is unresolved.** *Invalidated by:* no egress path and no gateway, which
would block the work setup entirely.

**A-02 — DR's platform permits one-shot Jobs, not only long-running Deployments.**
*Invalidated by:* a platform pipeline that only knows how to deploy Deployments. In that
case the worker-in-container design (a long-lived Temporal worker) becomes the better fit
**for DR only** — the home setup would keep the Job model, and the shared contract would
still hold, because the contract says nothing about container lifetime.

**A-03 — Temporal Cloud's cost is tolerable for personal use.**
No pricing is asserted in this document. *Invalidated by:* a monthly floor that dwarfs the
rest of the home setup. Note that this would **not** invalidate the architecture: the home
orchestrator would become GitHub Actions or a scheduled trigger, and the harness contract
would be untouched. That the design survives this is itself evidence the repository
boundary is drawn in the right place.

**A-04 — A task fits in one bounded, unattended run.**
PR review feedback starts a new run; it does not resume an old one. *Invalidated by:*
finding that useful tasks routinely need mid-run human input, which would make resumable
sessions a v1 requirement rather than a future idea.

**A-05 — Compute cost is negligible next to token cost.**
*Invalidated by:* runs that are far longer or far more CPU-intensive than expected. Worth
measuring once real runs exist, because several decisions lean on it.

### 6.3 A note on the DR platform docs

The Backstage platform documentation at
`https://backstage.drintern.dk/docs/default/component/platform-docs` could not be read:
the page returns the Backstage SPA shell (HTTP 200) and the TechDocs API behind it returns
**HTTP 401**. It is authentication-gated.

Consequently **the DR half of the runtime section is deliberately thin.** The Kubernetes
Job mapping in [§3.2](#32-two-tier-execution) is an inference from how GKE platforms
usually work, not a statement about how DR's actually works. It must be confirmed against
the real docs before anything is built for the work setup.

### 6.4 Security note

An autonomous process holding push credentials to company source repositories and running
on DR's shared cluster warrants security and platform review before the work setup goes
live.

---

## 7. Open Questions

| # | Question | Options / Notes |
|---|---|---|
| OQ-01 | Where does the always-on dispatcher run at home? | **Deliberately left open.** Cloud Run service with `min-instances=1` (simplest; idle instances bill at a reduced rate — verify current pricing); always-on home hardware (zero marginal cloud cost, worse availability, more divergence from DR); or skip Temporal at home entirely and trigger from GitHub Actions. The last option is not a defeat — the harness contract is unaffected either way. |
| OQ-02 | Does DR's platform support one-shot Jobs? | **Blocked on the Backstage docs (§6.3).** The single fact most likely to change the work-setup recommendation. See A-02. |
| OQ-03 | Model credential and billing at DR — direct API key or internal gateway? | See A-01. Determines whether `ANTHROPIC_BASE_URL` is optional or mandatory at DR. |
| OQ-04 | Temporal Cloud pricing floor for personal use | See A-03. Check early — it is cheap to check and expensive to discover late. |
| OQ-05 | Does the runner own git operations, or the agent? | Direction is decided (runner — §3.1). Open in its details: branch naming scheme, commit trailers, PR body template, and what happens when the agent leaves the tree dirty in an unexpected way. |
| OQ-06 | Where does the Skill Pack live? | **Deferred 2026-09-03** — v1 bakes skills into the image, so this doesn't need answering yet. Revisit alongside §3.5 when runtime-selected skills come back. |
| OQ-07 | Cloud Run Jobs maximum task timeout | **Verify against current GCP documentation rather than assuming.** Determines whether long tasks need chunking. |
| OQ-08 | What does `/out` carry, and does it survive? | **Resolved 2026-09-03.** Nothing — `/out` is removed. `RunResult` is written to GCS (`task-output.json`, §4.3) instead, which survives the container by construction. |
| OQ-09 | IAM for the `{GCP_PID}-agents-data` bucket — who reads/writes what? | Dispatcher: write `task.json`, read `task-output.json`. Container: read `task.json`, write `task-output.json` and `trace.json`. A least-privilege split needs specifying before this ships. |
| OQ-10 | Retention on Task Files and Result Files | Cheap and harmless at personal scale; needs a lifecycle policy before volume or compliance makes it not-harmless. Not urgent for v1. |
| OQ-11 | How does the harness derive `branch_name`? | A deterministic slug of `prompt` (cheap, same input → same name always) vs. a small model call that summarises the task into a human-friendly name (nicer, non-deterministic, needs its own failure handling). Not yet decided. |
| OQ-12 | Is overwriting `task-output.json` (and now `trace.json`) on retry acceptable? | Since 2026-09-03 both files are keyed by `task_id`, not `run_id` (§4.3, §3.4), so a retried task loses its previous attempt's result *and* trace unless something else preserves them. Candidates if it turns out to matter: a per-run object alongside them, GCS object versioning on the bucket, or accepting the loss. Not urgent until retries are actually implemented. |

---

## 8. Not Doing (and Why)

- **Dumb-pipe-only observability** — a container that emits nothing but stdout and an exit
  code would be maximally portable, and it was seriously considered. Rejected: progress
  visibility during a run (US-02) is worth the coupling, and the sink plugin keeps that
  coupling optional.
- **Worker-in-container** (the container *is* a long-lived Temporal worker) — genuinely
  simpler in several ways: one tier instead of two, native heartbeats, native
  cancellation, no launcher activity to write. **Rejected only because it cannot scale to
  zero at home.** If DR ever diverges, or if A-02 proves false, this is the design to
  reach for there. Recorded here so that reasoning is not lost.
- **A git-host adapter** — unnecessary. GitHub cloud on both sides (§3.6).
- ~~**Object-store I/O**~~ — **reversed 2026-09-03.** GCS now carries the Task File and
  Result File ([§3.3](#33-portability-as-a-contract-not-as-an-artifact),
  [§4.4](#44-environment-variable-contract), [§6.1](#61-constraints)). What's still
  rejected: object storage for *code* or workspace state — that stays git-only. The
  commented-out `gcloud` **CLI** install in the Dockerfile is still a fossil and should
  still go, but for a different reason now: GCS access is via the `google-cloud-storage`
  Python client (same pattern as `google-cloud-secret-manager` in `gcp_secrets.py`), not
  the `gcloud` CLI.
- **A database-backed task store (Firestore, etc.)** — considered as the reference-based
  alternative to a Task File. Rejected: it would add a second stateful dependency next to
  GCS rather than reusing the one the audit requirement already justifies, and a document
  that two writers (dispatcher, container) mutate over a run's lifetime is a weaker audit
  record than an object that's written once and never touched again.
- **Baked-in skills as the default** — kept as a documented fallback (§3.5), not the
  primary path.
- **Unpinned `latest` skills** — rejected outright. Non-reproducible and unreviewable.
- **Resumable sessions, warm pools, fan-out, multi-tenancy** — all deferred to §9. Each
  adds real state to a design whose main virtue is having none.
- **Structured `issue_ref`, `branch_name`, `skills_ref`, `harness`, `model`,
  `event_sink`/`event_sink_config`, `timeout_seconds` as Task File fields** — **removed
  2026-09-03** ([§4.1](#41-taskspec--the-input), [§4.4](#44-environment-variable-contract)).
  None of these are wrong ideas; each just assumes a choice this project doesn't have yet:
  a second harness or model to choose between, a second `EventSink` to route to, a real
  Skill Pack repo, a per-task timeout anyone could actually tune. Carrying the field before
  the choice exists is speculative configurability, not flexibility. See §9 for when each
  is worth reintroducing.

The through-line: this is a stateless, git-only, one-shot container, and nearly everything
excluded above was excluded because it would have added state.

---

## 9. Ideas for Future Versions

- **Fan-out.** One issue → N containers attempt it independently → N PRs → pick the best.
  Worth naming now because the current stateless, git-only design already permits it. The
  point is not to build it, but to avoid accidentally designing it out.
- **Resumable sessions.** Would allow mid-run human input and cheaper recovery from
  failure. Requires persisting session state between container lifetimes — the single
  biggest departure from the current model.
- **Warm pool at DR.** Pre-cloned repository caches and live workers, trading scale-to-zero
  for latency. Only ever makes sense at work, and is a clean example of a decision that
  must *not* be shared between the two environments.
- **Multi-tenant capability.** Other DR teams point it at their own repositories. Requires
  per-repo identity, quota, audit and cost attribution — none of which are needed at home.
- **Additional harness adapters** (Codex, Gemini CLI) — the real proof that `Harness` is an
  abstraction rather than a single-implementation interface. Until a second adapter exists,
  assume it leaks.
- **Runtime-selected skills (§3.5).** Pinned-ref-from-the-orchestrator was the original
  decision and the reasoning still holds; it's deferred, not wrong, until there's an actual
  Skill Pack repo and a second environment to justify it.
- **`EventSink` plugins (Temporal, HTTP).** Worth building the day there's a second
  consumer of Agent Events; `stdout` alone is enough while there's only one.
- **Per-task `timeout_seconds`.** Revisit once the platform-level Cloud Run Job timeout
  (OQ-07) proves too coarse for some real task.
- **A richer spec pointer than free-form `prompt`.** If specs routinely live somewhere
  queryable (issues, a doc system), a structured reference may earn its keep again — only
  once that pattern is real, not speculative.

---

## Appendix A — Current repo state vs. target

Concrete deltas between what exists today and what this document describes, so the
document is actionable rather than aspirational.

| Location | Today | Needed |
|---|---|---|
| `runner/harness/harness.py` | `Harness` protocol has only `build_command()`. It abstracts *launching* a CLI but not *reading* one. | A `parse()` counterpart producing `AgentEvent`s (§3.4, §4.2). |
| `runner/main.py:17-25` | Parses Claude Code's `stream-json` shape inline — `type == "assistant"`, `message.content[0]`, `thinking`/`text`. | Move into the Claude adapter. This is the leak `parse()` fixes; pointing the runner at another CLI today breaks it. |
| `runner/main.py` | **Done (2026-09-03).** `resolve_task()` reads `TASK_ID`, derives the bucket from `GCP_PID`, fetches `coder/{task_id}/task.json` via `runner/gcp_storage.py`, and builds the harness command from `task.prompt`. `run_command()` is also given the `trace.json` destination (§3.4). | Still missing: clone, branch, skills, commit, push, PR, `RunResult` — the rest of the lifecycle in §3.1. |
| `runner/harness/harness.py` | **Done (2026-09-03).** `run_command()` collects every raw stdout line and, best-effort, uploads it as `trace.json` (§3.4). Also now tolerant of a non-JSON stdout line (previously an unhandled `json.JSONDecodeError` would crash the whole run). | The rest of `parse()` → `AgentEvent` (§4.2) is still unbuilt — `trace.json` is a stand-in, not that. |
| — | No `RunResult`, no exit code taxonomy, no `task-output.json` write. | §4.3 and §4.5. |
| `runner/model/task.py` | **Done, then revised again outside this doc pass.** `TaskSpec.from_json()` / `from_dict()` parse `task_id`, `repo_url`, `prompt`, `base_branch` from camelCase JSON keys (§4.1). **Inconsistency to fix:** `repo_url` is read via `task_details["repoURL"]` — unconditional indexing, not `.get()` — so a Task File missing `repoURL` raises a raw `KeyError` instead of the same clean `ValueError` every other required field gets. | Add `repoURL` to the validated `required` list alongside `taskId`/`prompt`. |
| `runner/gcp_storage.py` | **Done (2026-09-03).** `get_object()` and `put_object()`, mirroring `gcp_secrets.py`. | — |
| `Dockerfile` | Creates `/workspace /task /out`. | `/workspace` stays. `/task` and `/out` are both removed: `/out` per OQ-08 (resolved — `RunResult` goes to GCS); `/task` was already unused and stays unused now that the Task File is resolved from GCS, not a mounted path. |
| `Dockerfile` | Commented-out `gcloud` install. | Remove the commented CLI install — GCS access is via the `google-cloud-storage` Python client, not the `gcloud` CLI (see §8). |
| `Dockerfile` | No `gh` CLI. | Needed for the lifecycle in §3.1. A Skill Pack fetch step is **not** needed for v1 — skills are baked into the image (§3.5). |
| `requirements.txt` | **Done (2026-09-03).** `google-cloud-storage` added alongside `google-cloud-secret-manager`. | — |

What is already right and should not be disturbed: the non-root `agent` user, the absence
of any credential in the image, the `Harness` protocol as a concept, and
`node:22-bookworm-slim` with `git` and `ripgrep` present.
