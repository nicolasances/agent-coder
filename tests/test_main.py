import json

from runner.exit_codes import EXIT_INFRA_FAILURE, EXIT_OK, EXIT_TASK_FAILED, EXIT_TIMEOUT
from runner.main import parse_task_id, run_queued


class FakeReceived:
    def __init__(self, data: str):
        self.data = data


class FakeQueue:
    def __init__(self, received: FakeReceived | None):
        self.received = received
        self.acked = 0
        self.nacked = 0
        self.extended = 0

    def extend(self) -> bool:
        self.extended += 1

        return True

    def pull_one(self):
        return self.received

    def ack(self) -> bool:
        self.acked += 1

        return True

    def nack(self) -> bool:
        self.nacked += 1

        return True


def test_parse_task_id_reads_task_id_from_the_message_body():
    assert parse_task_id(json.dumps({"taskId": "t-42"})) == "t-42"


def test_parse_task_id_rejects_a_body_without_task_id():
    try:
        parse_task_id("{}")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_parse_task_id_rejects_non_json():
    try:
        parse_task_id("not json")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_empty_pull_exits_zero_without_running_anything():
    queue = FakeQueue(None)
    executed = []

    code = run_queued(queue, lambda task_id: executed.append(task_id) or EXIT_OK)

    assert code == EXIT_OK
    assert executed == []
    assert queue.acked == 0 and queue.nacked == 0


def test_successful_run_acks_the_message():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    code = run_queued(queue, lambda task_id: EXIT_OK)

    assert code == EXIT_OK
    assert queue.acked == 1 and queue.nacked == 0


def test_the_task_id_from_the_message_is_what_gets_executed():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))
    executed = []

    run_queued(queue, lambda task_id: executed.append(task_id) or EXIT_OK)

    assert executed == ["t1"]


def test_task_failure_is_acked_so_it_is_not_retried():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    code = run_queued(queue, lambda task_id: EXIT_TASK_FAILED)

    assert code == EXIT_TASK_FAILED
    assert queue.acked == 1 and queue.nacked == 0


def test_timeout_is_acked():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    code = run_queued(queue, lambda task_id: EXIT_TIMEOUT)

    assert code == EXIT_TIMEOUT
    assert queue.acked == 1 and queue.nacked == 0


def test_infra_failure_exit_code_is_nacked_for_retry():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    code = run_queued(queue, lambda task_id: EXIT_INFRA_FAILURE)

    assert code == EXIT_INFRA_FAILURE
    assert queue.nacked == 1 and queue.acked == 0


def test_an_exception_while_executing_becomes_an_infra_failure_and_is_nacked():
    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    def explode(task_id: str) -> int:
        raise RuntimeError("clone failed")

    code = run_queued(queue, explode)

    assert code == EXIT_INFRA_FAILURE
    assert queue.nacked == 1 and queue.acked == 0


def test_a_malformed_message_is_acked_as_task_failed_because_retrying_cannot_fix_it():
    queue = FakeQueue(FakeReceived("garbage"))
    executed = []

    code = run_queued(queue, lambda task_id: executed.append(task_id) or EXIT_OK)

    assert code == EXIT_TASK_FAILED
    assert executed == []
    assert queue.acked == 1 and queue.nacked == 0


def test_local_mode_maps_an_exception_to_an_infra_failure_exit_code():
    from runner.main import run_local

    def explode(task_id: str) -> int:
        raise RuntimeError("secret manager unreachable")

    assert run_local("t1", explode) == EXIT_INFRA_FAILURE


def test_local_mode_returns_the_exit_code_of_the_run():
    from runner.main import run_local

    assert run_local("t1", lambda task_id: EXIT_TASK_FAILED) == EXIT_TASK_FAILED


def test_the_lease_is_extended_while_the_task_runs():
    import time

    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    def slow_run(task_id: str) -> int:
        time.sleep(0.2)

        return EXIT_OK

    run_queued(queue, slow_run, heartbeat_interval_seconds=0.02)

    assert queue.extended >= 2


def test_the_lease_stops_being_extended_once_the_task_is_settled():
    import time

    queue = FakeQueue(FakeReceived('{"taskId": "t1"}'))

    run_queued(queue, lambda task_id: EXIT_OK, heartbeat_interval_seconds=0.02)
    extended_at_settle = queue.extended
    time.sleep(0.1)

    assert queue.extended == extended_at_settle


def test_task_timeout_defaults_to_three_hours(monkeypatch):
    from runner.main import task_timeout_seconds

    monkeypatch.delenv("TASK_TIMEOUT_SECONDS", raising=False)

    assert task_timeout_seconds() == 10800


def test_task_timeout_can_be_overridden_by_the_environment(monkeypatch):
    from runner.main import task_timeout_seconds

    monkeypatch.setenv("TASK_TIMEOUT_SECONDS", "120")

    assert task_timeout_seconds() == 120


# --- Skills are installed before anything else runs (docs/features/skills-at-startup.md) ---

def test_execute_task_exits_30_and_never_starts_the_agent_when_skills_install_fails():
    from unittest.mock import patch

    from runner import main as runner_main
    from runner.skills import SkillsInstallError

    with patch.object(runner_main, "install_skills", side_effect=SkillsInstallError("boom")), patch.object(runner_main, "Claude") as mock_claude, patch.object(runner_main, "resolve_task") as mock_resolve_task, patch.object(runner_main, "GitOps") as mock_git_ops:
        exit_code = runner_main.execute_task("t1")

    assert exit_code == EXIT_INFRA_FAILURE
    mock_claude.assert_not_called()
    mock_resolve_task.assert_not_called()
    mock_git_ops.assert_not_called()


def test_execute_task_installs_skills_before_running_the_harness():
    from unittest.mock import MagicMock, patch

    from runner import main as runner_main

    calls = []
    harness = MagicMock()
    harness.run_task.side_effect = lambda *a, **k: calls.append("run_task") or 0

    with patch.object(runner_main, "install_skills", side_effect=lambda: calls.append("install_skills")), patch.object(runner_main, "Claude") as mock_claude, patch.object(runner_main, "harness_init"), patch.object(runner_main, "resolve_task"), patch.object(runner_main, "GitOps"), patch.object(runner_main, "gh_runner"), patch.object(runner_main, "open_pr_exists_for_issue", return_value=False):
        mock_claude.return_value.initialize.return_value = harness

        exit_code = runner_main.execute_task("t1")

    assert exit_code == EXIT_OK
    assert calls == ["install_skills", "run_task"]
