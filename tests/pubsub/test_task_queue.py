import pytest

from runner.pubsub.task_queue import TaskQueue

SUBSCRIPTION_PATH = "projects/toto-dev/subscriptions/agentcodertasks-sub"


class FakeMessage:
    def __init__(self, data: bytes):
        self.data = data


class FakeReceived:
    def __init__(self, ack_id: str, data: bytes):
        self.ack_id = ack_id
        self.message = FakeMessage(data)


class FakeResponse:
    def __init__(self, received_messages: list):
        self.received_messages = received_messages


class FakeSubscriber:
    """Records every call; optionally fails the unary calls like an exactly-once subscription can."""

    def __init__(self, received_messages: list | None = None, fail_with: Exception | None = None):
        self.received_messages = received_messages or []
        self.fail_with = fail_with
        self.pull_requests: list = []
        self.ack_requests: list = []
        self.modack_requests: list = []

    def pull(self, request: dict):
        self.pull_requests.append(request)

        return FakeResponse(self.received_messages)

    def acknowledge(self, request: dict):
        self.ack_requests.append(request)

        if self.fail_with:
            raise self.fail_with

    def modify_ack_deadline(self, request: dict):
        self.modack_requests.append(request)

        if self.fail_with:
            raise self.fail_with


def make_queue(subscriber: FakeSubscriber) -> TaskQueue:
    return TaskQueue("toto-dev", "agentcodertasks-sub", client=subscriber)


def test_pull_one_asks_for_exactly_one_message():
    subscriber = FakeSubscriber([FakeReceived("a1", b'{"taskId": "t1"}')])
    queue = make_queue(subscriber)

    queue.pull_one()

    assert subscriber.pull_requests == [{"subscription": SUBSCRIPTION_PATH, "max_messages": 1}]


def test_pull_one_returns_none_on_empty_pull():
    queue = make_queue(FakeSubscriber([]))

    assert queue.pull_one() is None


def test_pull_one_returns_the_message_body_as_text():
    queue = make_queue(FakeSubscriber([FakeReceived("a1", b'{"taskId": "t1"}')]))

    received = queue.pull_one()

    assert received is not None
    assert received.data == '{"taskId": "t1"}'


def test_ack_acknowledges_the_pulled_message():
    subscriber = FakeSubscriber([FakeReceived("a1", b"{}")])
    queue = make_queue(subscriber)
    queue.pull_one()

    assert queue.ack() is True
    assert subscriber.ack_requests == [{"subscription": SUBSCRIPTION_PATH, "ack_ids": ["a1"]}]


def test_nack_sets_the_ack_deadline_to_zero():
    subscriber = FakeSubscriber([FakeReceived("a1", b"{}")])
    queue = make_queue(subscriber)
    queue.pull_one()

    assert queue.nack() is True
    assert subscriber.modack_requests == [{"subscription": SUBSCRIPTION_PATH, "ack_ids": ["a1"], "ack_deadline_seconds": 0}]


def test_extend_pushes_the_ack_deadline_out_to_600_seconds():
    subscriber = FakeSubscriber([FakeReceived("a1", b"{}")])
    queue = make_queue(subscriber)
    queue.pull_one()

    assert queue.extend() is True
    assert subscriber.modack_requests == [{"subscription": SUBSCRIPTION_PATH, "ack_ids": ["a1"], "ack_deadline_seconds": 600}]


def test_failed_ack_is_reported_not_raised():
    subscriber = FakeSubscriber([FakeReceived("a1", b"{}")], fail_with=RuntimeError("ack id expired"))
    queue = make_queue(subscriber)
    queue.pull_one()

    assert queue.ack() is False


def test_failed_extend_is_reported_not_raised():
    subscriber = FakeSubscriber([FakeReceived("a1", b"{}")], fail_with=RuntimeError("transient"))
    queue = make_queue(subscriber)
    queue.pull_one()

    assert queue.extend() is False


def test_ack_without_a_pulled_message_is_a_noop_failure():
    subscriber = FakeSubscriber([])
    queue = make_queue(subscriber)

    assert queue.ack() is False
    assert subscriber.ack_requests == []


def test_from_env_reads_the_subscription_from_the_toto_project_in_gcp_pid(monkeypatch):
    monkeypatch.setenv("GCP_PID", "toto-dev")
    monkeypatch.setenv("PUBSUB_SUBSCRIPTION", "agentcodertasks-sub")
    monkeypatch.setenv("PUBSUB_PROJECT_ID", "gke-project")

    queue = TaskQueue.from_env(client=FakeSubscriber([]))

    assert queue.subscription_path == "projects/toto-dev/subscriptions/agentcodertasks-sub"


def test_from_env_requires_gcp_pid(monkeypatch):
    monkeypatch.delenv("GCP_PID", raising=False)
    monkeypatch.setenv("PUBSUB_SUBSCRIPTION", "agentcodertasks-sub")

    with pytest.raises(RuntimeError):
        TaskQueue.from_env(client=FakeSubscriber([]))


def test_from_env_requires_the_subscription(monkeypatch):
    monkeypatch.setenv("GCP_PID", "toto-dev")
    monkeypatch.delenv("PUBSUB_SUBSCRIPTION", raising=False)

    with pytest.raises(RuntimeError):
        TaskQueue.from_env(client=FakeSubscriber([]))
