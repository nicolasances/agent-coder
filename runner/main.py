import os

from runner.gcp_storage import get_object
from runner.git.gitops import GitOps
from runner.harness.harness import HarnessInit
from runner.model.task import TaskSpec

from .harness.claude import Claude

# This container's identity within the shared agent-tasks bucket. Fixed, not
# configurable — it names *this* repo, not a per-deployment choice.
# Layout: gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json (docs/concept.md §4.1, §4.4).
AGENT_NAME = "coder"

def task_object_path(task_id: str, filename: str) -> str:
    return f"{AGENT_NAME}/{task_id}/{filename}"

def agent_bucket() -> str:
    return f"{os.environ.get('GCP_PID')}-agents-data"

def resolve_task() -> TaskSpec:
    """Resolve the TaskSpec for this run from its Task File in GCS."""

    task_id = os.environ.get("TASK_ID")

    if not task_id:
        raise ValueError("TASK_ID is not set.")

    task_json = get_object(agent_bucket(), task_object_path(task_id, "task.json"))

    return TaskSpec.from_json(task_json)

def harness_init() -> HarnessInit: 

    task_id= os.environ.get("TASK_ID")

    if not task_id:
        raise ValueError("TASK_ID is not set.")

    return HarnessInit(
        agent_data_bucket=agent_bucket(),
        trace_object_path=task_object_path(task_id, "trace.json"),
    )


def main() -> int:


    # 1. Load the harness
    harness = Claude().initialize(harness_init())

    # 3. Resolve the task from its Task File in GCS
    task = resolve_task()

    # 4. Clone the repo
    git_ops = GitOps(repoURL=task.repo_url, branch=task.base_branch)

    git_ops.clone_repo()

    # 5. Build and run the command in the cloned repo, tracing every stdout line to GCS
    return harness.run_task(task, workdir=git_ops.local_path)


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
