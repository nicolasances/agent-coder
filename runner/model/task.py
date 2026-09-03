import json


class TaskSpec:
    """
    Models the TaskSpec described in docs/concept.md §4.1 — the input to one run.

    Delivered as a JSON object in GCS (the Task File — docs/concept.md §4.1, §4.4),
    resolved by the container via the TASK_ID execution override. This class only
    knows how to parse and validate that JSON; fetching the object from GCS is the
    caller's responsibility, not this class's.

    Deliberately minimal for v1: skills_ref, harness, model, event_sink and
    timeout_seconds are all hardcoded elsewhere for now rather than accepted here —
    see docs/concept.md §8 for why each was deferred rather than built.
    """

    task_id: str  # Stable id from the orchestrator. Idempotency key; must match the Task File's object name.
    repo_url: str  # HTTPS clone URL.
    prompt: str  # The task, in the orchestrator's own words. May point at an issue, a doc, or just be the instructions.
    base_branch: str  # Default "main".

    def __init__(
        self,
        task_id: str,
        repo_url: str,
        prompt: str,
        base_branch: str = "main",
    ) -> None:
        self.task_id = task_id
        self.repo_url = repo_url
        self.prompt = prompt
        self.base_branch = base_branch

    @staticmethod
    def from_dict(task_details: dict) -> "TaskSpec":
        """Build a TaskSpec from an already-parsed Task File (docs/concept.md §4.1, §4.4)."""

        required = ["taskId", "prompt"]
        missing = [field for field in required if not task_details.get(field)]

        if missing:
            raise ValueError(f"The Task File is missing required field(s): {', '.join(missing)}.")

        return TaskSpec(
            task_id=task_details["taskId"],
            repo_url=task_details["repoURL"],
            prompt=task_details["prompt"],
            base_branch=task_details.get("baseBranch", "main"),
        )

    @staticmethod
    def from_json(task_json: str) -> "TaskSpec":
        """Build a TaskSpec from the raw JSON text of a Task File.

        Takes JSON content, not a file path — the Task File lives in GCS
        (docs/concept.md §4.1), not on local disk. Fetching the object's bytes
        is the caller's job (e.g. a future runner/gcp_storage.py, mirroring the
        existing runner/gcp_secrets.py).
        """
        return TaskSpec.from_dict(json.loads(task_json))
