import os

from runner.gcp_storage import get_object
from runner.model.task import TaskSpec

from .harness.claude import Claude

# This container's identity within the shared agent-tasks bucket. Fixed, not
# configurable — it names *this* repo, not a per-deployment choice.
# Layout: gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json (docs/concept.md §4.1, §4.4).
AGENT_NAME = "coder"


def task_bucket() -> str:
    return f"{os.environ.get('GCP_PID')}-agents-data"


def task_object_path(task_id: str, filename: str) -> str:
    return f"{AGENT_NAME}/{task_id}/{filename}"


def resolve_task() -> TaskSpec:
    """Resolve the TaskSpec for this run from its Task File in GCS."""

    task_id = os.environ.get("TASK_ID")

    if not task_id:
        raise ValueError("TASK_ID is not set.")

    task_json = get_object(task_bucket(), task_object_path(task_id, "task.json"))

    return TaskSpec.from_json(task_json)


def main() -> int:

    # 1. Load the harness
    harness = Claude().initialize()

    # 3. Resolve the task from its Task File in GCS
    task = resolve_task()

    # 4. Build and run the command, tracing every stdout line to GCS
    return harness.run_task(
        task,
        trace_bucket=task_bucket(),
        trace_object=task_object_path(task.task_id, "trace.json"),
    )


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
