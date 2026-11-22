import pytest

from runner.exit_codes import EXIT_SIGTERM
from runner.shutdown import SigtermGuard


class FakeQueue:
    def __init__(self):
        self.nacked = 0

    def nack(self) -> bool:
        self.nacked += 1

        return True


class FakeHarness:
    def __init__(self):
        self.stopped = 0

    def stop(self) -> None:
        self.stopped += 1


def test_sigterm_stops_the_agent_nacks_and_exits():
    queue = FakeQueue()
    harness = FakeHarness()
    guard = SigtermGuard(queue)
    guard.harness = harness

    with pytest.raises(SystemExit) as exit_info:
        guard.handle(15, None)

    assert exit_info.value.code == EXIT_SIGTERM
    assert harness.stopped == 1
    assert queue.nacked == 1


def test_sigterm_before_the_agent_started_still_nacks_and_exits():
    queue = FakeQueue()
    guard = SigtermGuard(queue)

    with pytest.raises(SystemExit):
        guard.handle(15, None)

    assert queue.nacked == 1


def test_sigterm_in_local_mode_has_no_queue_to_nack():
    guard = SigtermGuard(None)

    with pytest.raises(SystemExit) as exit_info:
        guard.handle(15, None)

    assert exit_info.value.code == EXIT_SIGTERM
