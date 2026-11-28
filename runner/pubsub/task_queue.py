"""Pulls exactly one task from a Pub/Sub subscription and settles it.

KEDA starts the pod but does not pass it the message, so the pod pulls its own task.
Synchronous pull with max_messages=1, deliberately not streaming pull: streaming pull
leases and holds extra messages this pod will never process.

The subscription has exactly-once delivery, so ack and modify-ack-deadline can fail
explicitly (e.g. the lease already expired). Those failures are logged and reported as
False, never raised: a failed ack must not crash a finished run.
"""

import os

from google.cloud import pubsub_v1

LEASE_SECONDS = 600  # Pub/Sub's maximum ack deadline.


class ReceivedTask:
    def __init__(self, ack_id: str, data: str):
        self.ack_id = ack_id
        self.data = data


class TaskQueue:

    def __init__(self, project_id: str, subscription: str, client=None):
        self.subscription_path = f"projects/{project_id}/subscriptions/{subscription}"
        self.client = client if client is not None else pubsub_v1.SubscriberClient()
        self.ack_id: str | None = None

    @staticmethod
    def from_env(client=None) -> "TaskQueue":
        """The subscription lives in the toto project (GCP_PID), like every other Toto topic (issue #12)."""

        project_id = os.environ.get("GCP_PID")
        subscription = os.environ.get("PUBSUB_SUBSCRIPTION")

        if not project_id or not subscription:
            raise RuntimeError("GCP_PID and PUBSUB_SUBSCRIPTION must be set when TASK_ID is not.")

        return TaskQueue(project_id, subscription, client)

    def pull_one(self) -> ReceivedTask | None:
        response = self.client.pull(request={"subscription": self.subscription_path, "max_messages": 1})

        if not response.received_messages:
            return None

        received = response.received_messages[0]
        self.ack_id = received.ack_id

        return ReceivedTask(received.ack_id, received.message.data.decode("utf-8"))

    def ack(self) -> bool:
        if not self.ack_id:
            print("Cannot ack: no message has been pulled.", flush=True)

            return False

        try:
            self.client.acknowledge(request={"subscription": self.subscription_path, "ack_ids": [self.ack_id]})
        except Exception as e:
            print(f"Failed to ack the message: {e}", flush=True)

            return False

        return True

    def nack(self) -> bool:
        return self._modify_ack_deadline(0, "nack")

    def extend(self, seconds: int = LEASE_SECONDS) -> bool:
        return self._modify_ack_deadline(seconds, "extend the lease of")

    def _modify_ack_deadline(self, seconds: int, what: str) -> bool:
        if not self.ack_id:
            print(f"Cannot {what} the message: none has been pulled.", flush=True)

            return False

        try:
            self.client.modify_ack_deadline(request={"subscription": self.subscription_path, "ack_ids": [self.ack_id], "ack_deadline_seconds": seconds})
        except Exception as e:
            print(f"Failed to {what} the message: {e}", flush=True)

            return False

        return True
