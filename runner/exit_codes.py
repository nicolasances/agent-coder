"""Exit code taxonomy (docs/concept.md §4.5). The code drives the Pub/Sub ack/nack decision."""

EXIT_OK = 0  # PR opened. Ack.
EXIT_NO_CHANGE = 10  # The agent concluded nothing was required. Ack.
EXIT_TASK_FAILED = 20  # The agent could not solve it. Ack: retrying only burns tokens.
EXIT_VALIDATION_FAILED = 21  # Changes were produced but did not pass checks. Ack.
EXIT_INFRA_FAILURE = 30  # Clone, secrets, GCS, push, model unreachable. Nack: worth retrying.
EXIT_TIMEOUT = 40  # TASK_TIMEOUT_SECONDS elapsed. Ack.
EXIT_SIGTERM = 143  # Conventional 128 + SIGTERM. Never acked: the message is nacked on the way out.

TAXONOMY = {EXIT_OK, EXIT_NO_CHANGE, EXIT_TASK_FAILED, EXIT_VALIDATION_FAILED, EXIT_INFRA_FAILURE, EXIT_TIMEOUT}


def map_harness_exit(harness_exit_code: int) -> int:
    """Map whatever the agent CLI returned onto the taxonomy.

    A code already in the taxonomy passes through. Any other non-zero code is a failed task:
    the CLI gives us no way to tell "could not solve it" from "model unreachable", so the
    cautious reading is "do not retry" (retrying a 3 hour run is the expensive mistake).
    """

    if harness_exit_code in TAXONOMY:
        return harness_exit_code

    return EXIT_TASK_FAILED


def should_nack(exit_code: int) -> bool:
    """Only an infra failure is worth redelivering."""

    return exit_code == EXIT_INFRA_FAILURE
