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

    The task is always a GitHub issue, never free-form instructions (issue #5): a run
    is by construction the implementation of one reviewable, addressable unit of work.
    """

    task_id: str  # Stable id from the orchestrator. Idempotency key; must match the Task File's object name.
    repo_url: str  # HTTPS clone URL.
    issue_url: str  # The GitHub issue this run implements. The only thing that varies what the agent is asked to do.
    base_branch: str  # Default "main".

    def __init__(self, task_id: str, repo_url: str, issue_url: str, base_branch: str = "main") -> None:
        self.task_id = task_id
        self.repo_url = repo_url
        self.issue_url = issue_url
        self.base_branch = base_branch

    @staticmethod
    def from_dict(task_details: dict) -> "TaskSpec":
        """Build a TaskSpec from an already-parsed Task File (docs/concept.md §4.1, §4.4).

        Validation is presence-and-non-emptiness only — deliberately. The issue URL's
        shape is not parsed, and it is not checked against repo_url: a mismatch surfaces
        immediately anyway, since the agent clones one repo and cannot find the issue.
        See issue #5's "Out of Scope".
        """

        required = ["taskId", "repoURL", "issueURL"]
        missing = [field for field in required if not task_details.get(field)]

        if missing:
            raise ValueError(f"The Task File is missing required field(s): {', '.join(missing)}.")

        return TaskSpec(task_id=task_details["taskId"], repo_url=task_details["repoURL"], issue_url=task_details["issueURL"], base_branch=task_details.get("baseBranch", "main"))

    @staticmethod
    def from_json(task_json: str) -> "TaskSpec":
        """Build a TaskSpec from the raw JSON text of a Task File.

        Takes JSON content, not a file path — the Task File lives in GCS
        (docs/concept.md §4.1), not on local disk. Fetching the object's bytes
        is the caller's job (e.g. a future runner/gcp_storage.py, mirroring the
        existing runner/gcp_secrets.py).
        """

        return TaskSpec.from_dict(json.loads(task_json))
