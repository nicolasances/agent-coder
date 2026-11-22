import signal

from runner.exit_codes import EXIT_SIGTERM


class SigtermGuard:
    """On SIGTERM (pod eviction, scale-down): stop the agent, nack at once so the message
    is redelivered without waiting for the lease to expire, then exit.

    SystemExit is not an Exception, so it is not swallowed by the run's `except Exception`
    and the run cannot go on to ack the message it just nacked.
    """

    def __init__(self, queue):
        self.queue = queue  # None in local mode: nothing to nack.
        self.harness = None  # Set once the agent exists.

    def install(self) -> None:
        signal.signal(signal.SIGTERM, self.handle)

    def handle(self, signum, frame) -> None:
        print("SIGTERM received: stopping the agent and releasing the task.", flush=True)

        if self.harness is not None:
            self.harness.stop()

        if self.queue is not None:
            self.queue.nack()

        raise SystemExit(EXIT_SIGTERM)
