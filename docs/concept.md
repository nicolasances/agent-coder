# Coding Agent — Concept

> Status: concept / decision document. Nothing here is implemented yet.
> Last revised: 2026-08-31.

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

---

## 3. Features

### 3.1 The run lifecycle

The container performs a fixed sequence of phases. Naming them is the point: today
`runner/main.py` implements none of them — it builds a command, streams output, and stops.

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

**Design decision — the runner owns the git operations, not the agent.** The alternative
is to tell the agent, in its prompt, to commit and push and open a PR itself. That is
tempting because it is less code. It is rejected for three reasons:

1. **Determinism.** Branch naming, commit trailers and PR body formatting become code
   with tests, not prose the model may reinterpret.
2. **Credential blast radius.** If the runner performs the push, the push credential never
   needs to be reachable by the agent's shell. The agent edits files; it does not publish.
3. **Failure attribution.** "The agent could not solve the task" and "the push was
   rejected" are different outcomes with different retry semantics. Merging them into one
   opaque agent turn destroys that distinction.

This remains an open question only in its details (see OQ-05), not in its direction.

### 3.2 Two-tier execution

The orchestrator was chosen as Temporal. That choice collides directly with the
scale-to-zero constraint, and resolving the collision is what determines the architecture.

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

1. Outbound network — to GitHub, and to the model endpoint.
2. An ephemeral writable disk for `/workspace`.
3. Secrets injected as environment variables at execution time.

That is the entire list. No volumes, no PVCs, no object store, no service mesh, no
ingress. This is a direct consequence of choosing git as the only I/O channel, and it is
why the choice between Cloud Run Jobs and Kubernetes Jobs is nearly a non-decision — both
provide all three without effort.

The portable interface is therefore three things, all specified in [§4](#4-data-models):

- the **environment variable contract** (input),
- the **exit code taxonomy** (outcome),
- the **stdout NDJSON event stream** (observation).

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

**Decision: pinned ref, resolved by the orchestrator.**

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

### 3.6 Extension seams

Exactly two, for v1:

| Seam | Varies | Implementations |
|---|---|---|
| `Harness` | Which agent CLI | Claude Code (v1). Codex, Gemini CLI later. |
| `EventSink` | Where events go | `stdout` (always), `temporal`, `http`, `none`. |

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

Supplied by the orchestrator, delivered as environment variables (see
[§4.4](#44-environment-variable-contract)).

| Field | Type | Notes |
|---|---|---|
| `task_id` | string | Stable id from the orchestrator. Idempotency key. |
| `repo_url` | string | HTTPS clone URL. |
| `issue_ref` | string \| null | e.g. `owner/repo#123`. Null for a free-form task. |
| `prompt` | string \| null | Free-form task text. One of `issue_ref` or `prompt` is required. |
| `base_branch` | string | Default `main`. |
| `branch_name` | string | Computed by the orchestrator so it is recorded before the run starts. |
| `skills_ref` | string | Tag, branch or SHA. |
| `harness` | enum | `claude` for v1. |
| `model` | string | Passed through to the CLI. |
| `event_sink` | enum | `stdout` \| `temporal` \| `http` \| `none`. |
| `timeout_seconds` | int | Runner self-terminates; a belt-and-braces backstop to the platform's own timeout. |

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

Written to `/out/result.json` and emitted on the event stream at termination.

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

This table *is* the portable input surface. Anything not here is not an input.

| Variable | Required | Notes |
|---|---|---|
| `TASK_ID` | yes | |
| `REPO_URL` | yes | |
| `ISSUE_REF` | one of | |
| `TASK_PROMPT` | one of | |
| `BASE_BRANCH` | no | default `main` |
| `BRANCH_NAME` | yes | |
| `SKILLS_REPO_URL` | yes | |
| `SKILLS_REF` | yes | no default — an unset ref must fail loudly, never silently mean `latest` |
| `HARNESS` | no | default `claude` |
| `MODEL` | no | |
| `EVENT_SINK` | no | default `stdout` |
| `EVENT_SINK_CONFIG` | conditional | JSON; e.g. Temporal task token, or HTTP endpoint |
| `TIMEOUT_SECONDS` | no | |
| `GITHUB_TOKEN` | yes | secret, injected at execution |
| `ANTHROPIC_API_KEY` | yes | secret, injected at execution |
| `ANTHROPIC_BASE_URL` | no | set when routing via an internal gateway |

No credential is ever baked into the image. This is already true of the current Dockerfile
and must stay true.

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
- **Git-only I/O.** Clone in, push out. No volumes, no object store. This constraint is
  what makes the runtime decision cheap; loosening it would be expensive.
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
| OQ-06 | Where does the Skill Pack live? | Same repo (simple, couples skill releases to harness releases), separate repo (independent versioning, needs its own credential), or a released artifact. Affects `SKILLS_REPO_URL` and the DR egress question. |
| OQ-07 | Cloud Run Jobs maximum task timeout | **Verify against current GCP documentation rather than assuming.** Determines whether long tasks need chunking. |
| OQ-08 | What does `/out` carry, and does it survive? | Candidate: the `RunResult`. On Cloud Run Jobs and K8s Jobs the filesystem dies with the container, so `/out` is only useful if something reads it before exit — which may mean the event stream is the real result channel and `/out` is redundant. |

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
- **Object-store I/O** — superseded by git-only. The commented-out `gcloud` install in the
  Dockerfile is a fossil of this earlier model and should go.
- **Baked-in skills as the default** — kept as a documented fallback (§3.5), not the
  primary path.
- **Unpinned `latest` skills** — rejected outright. Non-reproducible and unreviewable.
- **Resumable sessions, warm pools, fan-out, multi-tenancy** — all deferred to §9. Each
  adds real state to a design whose main virtue is having none.

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

---

## Appendix A — Current repo state vs. target

Concrete deltas between what exists today and what this document describes, so the
document is actionable rather than aspirational.

| Location | Today | Needed |
|---|---|---|
| `runner/harness/harness.py` | `Harness` protocol has only `build_command()`. It abstracts *launching* a CLI but not *reading* one. | A `parse()` counterpart producing `AgentEvent`s (§3.4, §4.2). |
| `runner/main.py:17-25` | Parses Claude Code's `stream-json` shape inline — `type == "assistant"`, `message.content[0]`, `thinking`/`text`. | Move into the Claude adapter. This is the leak `parse()` fixes; pointing the runner at another CLI today breaks it. |
| `runner/main.py` | Hardcodes the prompt (`"Describe what you think this repo is about"`); implements none of the lifecycle in §3.1. | Read a `TaskSpec` from the environment; implement the lifecycle. |
| `runner/main.py` | Prints assistant text to stdout as prose. | Emit NDJSON `AgentEvent`s; add the `EventSink` seam. |
| — | No `RunResult`, no exit code taxonomy. | §4.3 and §4.5. |
| `Dockerfile` | Creates `/workspace /task /out`. | `/workspace` stays. `/task` appears unused under the env-var contract. `/out` needs a decided purpose or removal (OQ-08). |
| `Dockerfile` | Commented-out `gcloud` install. | Remove — dead under git-only I/O. |
| `Dockerfile` | No `gh` CLI, no Skill Pack fetch step. | Both needed for the lifecycle in §3.1. |

What is already right and should not be disturbed: the non-root `agent` user, the absence
of any credential in the image, the `Harness` protocol as a concept, and
`node:22-bookworm-slim` with `git` and `ripgrep` present.
