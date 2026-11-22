from runner.exit_codes import EXIT_INFRA_FAILURE, EXIT_NO_CHANGE, EXIT_OK, EXIT_TASK_FAILED, EXIT_TIMEOUT, EXIT_VALIDATION_FAILED, map_harness_exit, should_nack


def test_harness_success_maps_to_ok():
    assert map_harness_exit(0) == EXIT_OK


def test_harness_taxonomy_codes_pass_through_unchanged():
    for code in [EXIT_NO_CHANGE, EXIT_TASK_FAILED, EXIT_VALIDATION_FAILED, EXIT_INFRA_FAILURE, EXIT_TIMEOUT]:
        assert map_harness_exit(code) == code


def test_unknown_nonzero_harness_exit_maps_to_task_failed():
    assert map_harness_exit(1) == EXIT_TASK_FAILED


def test_only_infra_failure_is_nacked():
    assert should_nack(EXIT_INFRA_FAILURE) is True

    for code in [EXIT_OK, EXIT_NO_CHANGE, EXIT_TASK_FAILED, EXIT_VALIDATION_FAILED, EXIT_TIMEOUT]:
        assert should_nack(code) is False
