import threading
from typing import Callable

# Pub/Sub's maximum ack deadline is 600s; extending every 5 minutes leaves a full
# missed beat of slack before the lease can lapse.
HEARTBEAT_INTERVAL_SECONDS = 300


class LeaseHeartbeat:
    """Keeps a message lease alive in a background thread until stopped.

    A run lasts up to 3 hours, far beyond the 600s ack-deadline cap, so the lease has to be
    renewed for as long as the agent works. A failed or raising extend is logged by the
    caller / here and the beat carries on: one missed beat is survivable, a dead heartbeat
    thread would silently lose the lease and cause a duplicate 3 hour run.
    """

    def __init__(self, extend: Callable[[], bool], interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS):
        self.extend = extend
        self.interval_seconds = interval_seconds
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join()

    def _run(self) -> None:
        # Event.wait returns True as soon as stop() is called, so stop() never waits a full interval.
        while not self._stopped.wait(self.interval_seconds):
            try:
                if not self.extend():
                    print("Lease extension was not accepted; will try again on the next beat.", flush=True)
            except Exception as e:
                print(f"Lease extension raised: {e}", flush=True)
