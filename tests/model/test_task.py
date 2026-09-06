import json

import pytest

from runner.model.task import TaskSpec


def test_from_dict_reads_the_issue_url_from_the_issueURL_key():
    task = TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "issueURL": "https://github.com/acme/widgets/issues/7"})

    assert task.issue_url == "https://github.com/acme/widgets/issues/7"


def test_from_dict_defaults_the_base_branch_to_main():
    task = TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "issueURL": "https://github.com/acme/widgets/issues/7"})

    assert task.base_branch == "main"


def test_from_dict_reads_an_explicit_base_branch():
    task = TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "issueURL": "https://github.com/acme/widgets/issues/7", "baseBranch": "develop"})

    assert task.base_branch == "develop"


def test_from_dict_rejects_a_task_file_without_an_issue_url():
    with pytest.raises(ValueError, match="issueURL"):
        TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git"})


def test_from_dict_rejects_a_task_file_that_still_carries_a_prompt_instead_of_an_issue_url():
    # The hard cut: `prompt` is not a fallback. A Task File written by a stale
    # dispatcher is simply a Task File missing `issueURL`.
    with pytest.raises(ValueError, match="issueURL"):
        TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "prompt": "go and fix the thing"})


def test_from_dict_rejects_a_missing_repo_url_with_a_value_error_not_a_key_error():
    # docs/concept.md Appendix A: `repoURL` was read via unconditional indexing,
    # so its absence raised a raw KeyError instead of the clean ValueError every
    # other required field gets.
    with pytest.raises(ValueError, match="repoURL"):
        TaskSpec.from_dict({"taskId": "t-1", "issueURL": "https://github.com/acme/widgets/issues/7"})


def test_from_dict_rejects_a_missing_task_id():
    with pytest.raises(ValueError, match="taskId"):
        TaskSpec.from_dict({"repoURL": "https://github.com/acme/widgets.git", "issueURL": "https://github.com/acme/widgets/issues/7"})


def test_from_dict_names_every_missing_required_field_at_once():
    with pytest.raises(ValueError) as error:
        TaskSpec.from_dict({})

    message = str(error.value)

    assert "taskId" in message
    assert "repoURL" in message
    assert "issueURL" in message


def test_from_dict_rejects_an_empty_issue_url():
    with pytest.raises(ValueError, match="issueURL"):
        TaskSpec.from_dict({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "issueURL": ""})


def test_from_json_parses_the_raw_task_file_text():
    task_json = json.dumps({"taskId": "t-1", "repoURL": "https://github.com/acme/widgets.git", "issueURL": "https://github.com/acme/widgets/issues/7"})

    task = TaskSpec.from_json(task_json)

    assert task.task_id == "t-1"
    assert task.repo_url == "https://github.com/acme/widgets.git"
    assert task.issue_url == "https://github.com/acme/widgets/issues/7"
