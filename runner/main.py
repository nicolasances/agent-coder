import os

from runner.config.runner import RunnerConfig
from runner.gcp_storage import get_object
from runner.model.task import TaskSpec

from .harness.claude import Claude

# This container's identity within the shared agent-tasks bucket. Fixed, not
# configurable — it names *this* repo, not a per-deployment choice.
# Layout: gs://{GCP_PID}-agents-data/coder/{TASK_ID}/task.json (docs/concept.md §4.1, §4.4).
AGENT_NAME = "coder"


def resolve_task() -> TaskSpec:
    """Resolve the TaskSpec for this run from its Task File in GCS."""

    bucket = f"{os.environ.get("GCP_PID")}-agents-data"
    task_id = os.environ.get("TASK_ID")

    if not task_id:
        raise ValueError("TASK_ID is not set.")

    object_name = f"{AGENT_NAME}/{task_id}/task.json"
    task_json = get_object(bucket, object_name)

    return TaskSpec.from_json(task_json)


def main() -> int:

    harness = Claude()

    # 1. Load runner config (secrets)
    RunnerConfig.get_config(harness)

    # 2. Resolve the task from its Task File in GCS
    task = resolve_task()

    # 3. Build and run the command
    return harness.run_command(harness.build_command(task.prompt, model="haiku"))


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
