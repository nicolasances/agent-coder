import time

from runner.lease import LeaseHeartbeat


def wait_until(condition, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if condition():
            return True

        time.sleep(0.01)

    return False


def test_heartbeat_extends_the_lease_repeatedly_while_running():
    calls = []
    heartbeat = LeaseHeartbeat(lambda: calls.append(1) or True, interval_seconds=0.02)

    heartbeat.start()

    assert wait_until(lambda: len(calls) >= 3)

    heartbeat.stop()


def test_heartbeat_stops_extending_once_stopped():
    calls = []
    heartbeat = LeaseHeartbeat(lambda: calls.append(1) or True, interval_seconds=0.02)
    heartbeat.start()
    wait_until(lambda: len(calls) >= 1)

    heartbeat.stop()
    count_after_stop = len(calls)
    time.sleep(0.1)

    assert len(calls) == count_after_stop


def test_heartbeat_keeps_going_when_an_extend_reports_failure():
    calls = []
    heartbeat = LeaseHeartbeat(lambda: calls.append(1) or False, interval_seconds=0.02)

    heartbeat.start()

    assert wait_until(lambda: len(calls) >= 3)

    heartbeat.stop()


def test_heartbeat_keeps_going_when_an_extend_raises():
    calls = []

    def flaky() -> bool:
        calls.append(1)
        raise RuntimeError("network blip")

    heartbeat = LeaseHeartbeat(flaky, interval_seconds=0.02)

    heartbeat.start()

    assert wait_until(lambda: len(calls) >= 3)

    heartbeat.stop()
