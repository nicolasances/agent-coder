import os
from typing import Callable

from runner.exit_codes import EXIT_INFRA_FAILURE, EXIT_OK, EXIT_TASK_FAILED, map_harness_exit, should_nack
from runner.gcp_storage import get_object
from runner.git.gitops import GitOps
from runner.git.pr_check import gh_runner, open_pr_exists_for_issue
from runner.harness.harness import SECRET_NAME_CODING_AGENT_GH_TOKEN, HarnessInit
from runner.lease import HEARTBEAT_INTERVAL_SECONDS, LeaseHeartbeat
from runner.model.task import TaskSpec
from runner.model.task_message import TaskMessage
from runner.pubsub.task_queue import TaskQueue
from runner.shutdown import SigtermGuard
from runner.skills import SkillsInstallError, install_skills

from .harness.claude import Claude

# This container's identity within the shared agent-tasks bucket. Fixed, not
# configurable — it names *this* repo, not a per-deployment choice.
# Layout: gs://{GCP_PID}-agents-data/coder/{taskId}/task.json (docs/concept.md §4.1, §4.4).
AGENT_NAME = "coder"

# Internal bound on one run (US-05). Kubernetes' activeDeadlineSeconds (3h15m) is only the backstop.
DEFAULT_TASK_TIMEOUT_SECONDS = 10800

def task_timeout_seconds() -> int:
    return int(os.environ.get("TASK_TIMEOUT_SECONDS", DEFAULT_TASK_TIMEOUT_SECONDS))

def task_object_path(task_id: str, filename: str) -> str:
    return f"{AGENT_NAME}/{task_id}/{filename}"

def agent_bucket() -> str:
    return f"{os.environ.get('GCP_PID')}-agents-data"

def resolve_task(task_id: str) -> TaskSpec:
    """Resolve the TaskSpec for a task id from its Task File in GCS."""

    task_json = get_object(agent_bucket(), task_object_path(task_id, "task.json"))

    return TaskSpec.from_json(task_json)

def harness_init(task_id: str) -> HarnessInit:

    return HarnessInit(
        agent_data_bucket=agent_bucket(),
        trace_object_path=task_object_path(task_id, "trace.json"),
    )

def execute_task(task_id: str, guard: SigtermGuard | None = None) -> int:
    """Run one task end to end and return its exit code (docs/concept.md §4.5).

    Any exception raised here (GCS, Secret Manager, clone, ...) is an infra failure;
    the caller maps it to exit 30.
    """

    # 0. Install the latest skills. Without them the agent must not start: /implement etc. would be missing.
    try:
        install_skills()
    except SkillsInstallError as e:
        print(e)

        return EXIT_INFRA_FAILURE

    # 1. Load the harness
    harness = Claude().initialize(harness_init(task_id))

    if guard is not None:
        guard.harness = harness

    # 2. Resolve the task from its Task File in GCS
    task = resolve_task(task_id)

    # 3. Idempotency: a redelivered message must not start a second 3 hour run for the same issue
    if open_pr_exists_for_issue(task.issue_url, gh_runner(harness.secrets[SECRET_NAME_CODING_AGENT_GH_TOKEN])):
        print(f"An open PR already exists for {task.issue_url}: skipping the run.", flush=True)

        return EXIT_OK

    # 4. Clone the repo
    git_ops = GitOps(repoURL=task.repo_url, branch=task.base_branch)

    git_ops.clone_repo()

    # 5. Build and run the command in the cloned repo, tracing every stdout line to GCS
    return map_harness_exit(harness.run_task(task, workdir=git_ops.local_path, timeout_seconds=task_timeout_seconds()))

def run_local(task_id: str, execute: Callable[[str], int]) -> int:
    """Run one task with no queue: same exit-code mapping, nothing to ack."""

    try:
        return execute(task_id)
    except Exception as e:
        print(f"Infra failure while running task '{task_id}': {e}", flush=True)

        return EXIT_INFRA_FAILURE

def run_queued(queue: TaskQueue, execute: Callable[[str], int], heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS) -> int:
    """Pull one task, run it, and ack or nack the message by outcome."""

    received = queue.pull_one()

    if received is None:
        print("Nothing to pull: the subscription is empty. Exiting.", flush=True)

        return EXIT_OK

    try:
        message = TaskMessage.from_json(received.data)
    except ValueError as e:
        # Redelivering a malformed message can never fix it.
        print(f"Dropping malformed message: {e}", flush=True)
        queue.ack()

        return EXIT_TASK_FAILED

    task_id = message.task_id

    # The cid links this run to the request that queued it (e.g. in ape-tasks' logs).
    print(f"Pulled task '{task_id}' (cid: {message.cid}).", flush=True)

    # A run outlives Pub/Sub's 600s ack-deadline cap, so keep the lease alive until it ends.
    heartbeat = LeaseHeartbeat(queue.extend, heartbeat_interval_seconds)
    heartbeat.start()

    try:
        exit_code = execute(task_id)
    except Exception as e:
        print(f"Infra failure while running task '{task_id}': {e}", flush=True)
        exit_code = EXIT_INFRA_FAILURE
    finally:
        heartbeat.stop()

    if should_nack(exit_code):
        queue.nack()
    else:
        queue.ack()

    return exit_code

def main() -> int:

    local_task_id = os.environ.get("TASK_ID")

    # Local mode (US-04): run a container without an orchestrator or a queue.
    if local_task_id:
        guard = SigtermGuard(None)
        guard.install()

        return run_local(local_task_id, lambda task_id: execute_task(task_id, guard))

    queue = TaskQueue.from_env()
    guard = SigtermGuard(queue)
    guard.install()

    return run_queued(queue, lambda task_id: execute_task(task_id, guard))


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
