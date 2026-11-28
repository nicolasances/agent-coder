import json

TASK_REQUESTED = "taskRequested"


class TaskMessage:
    """
    The Task Message pulled from the queue: a Toto envelope (the `TotoMessage` that totoms
    publishes as JSON: {timestamp, cid, id, type, msg, data}) asking for one run.

    Only `type == "taskRequested"` with a non-empty `data.taskId` is a Task Message. The legacy
    raw body {"taskId": "<id>"} is not accepted anymore (issue #12): there is one contract, the
    Toto one, and producers publish through totoms (ape-tasks).

    `cid` is the correlation id of the request that queued the task. It is only used to trace a
    run back to that request in the logs, so a missing cid is not an error.
    """

    task_id: str
    cid: str | None

    def __init__(self, task_id: str, cid: str | None = None) -> None:
        self.task_id = task_id
        self.cid = cid

    @staticmethod
    def from_json(message_body: str) -> "TaskMessage":
        """Build a TaskMessage from the raw message body. Raises ValueError when it is not one."""

        try:
            envelope = json.loads(message_body)
        except json.JSONDecodeError as e:
            raise ValueError(f"The message body is not JSON: {e}")

        if not isinstance(envelope, dict):
            raise ValueError("The message body is not a Toto envelope (a JSON object).")

        if envelope.get("type") != TASK_REQUESTED:
            raise ValueError(f"The message type is '{envelope.get('type')}', expected '{TASK_REQUESTED}'.")

        data = envelope.get("data")
        task_id = data.get("taskId") if isinstance(data, dict) else None

        if not task_id:
            raise ValueError("The message has no 'data.taskId'.")

        return TaskMessage(task_id=task_id, cid=envelope.get("cid"))
