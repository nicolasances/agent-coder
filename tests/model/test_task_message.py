import json

import pytest

from runner.model.task_message import TaskMessage


def test_reads_the_task_id_from_the_data_of_a_toto_envelope():
    body = json.dumps({"timestamp": "2026.11.28 10:00:00", "cid": "cid-1", "id": "t-42", "type": "taskRequested", "msg": "Task requested", "data": {"taskId": "t-42"}})

    message = TaskMessage.from_json(body)

    assert message.task_id == "t-42"


def test_reads_the_correlation_id_of_the_envelope():
    body = json.dumps({"cid": "cid-1", "type": "taskRequested", "data": {"taskId": "t-42"}})

    message = TaskMessage.from_json(body)

    assert message.cid == "cid-1"


def test_a_missing_correlation_id_is_not_an_error():
    body = json.dumps({"type": "taskRequested", "data": {"taskId": "t-42"}})

    message = TaskMessage.from_json(body)

    assert message.cid is None


def test_rejects_the_legacy_top_level_task_id_shape():
    with pytest.raises(ValueError):
        TaskMessage.from_json(json.dumps({"taskId": "t-42"}))


def test_rejects_an_envelope_of_another_type():
    body = json.dumps({"cid": "cid-1", "type": "somethingElse", "data": {"taskId": "t-42"}})

    with pytest.raises(ValueError):
        TaskMessage.from_json(body)


def test_rejects_an_envelope_without_a_task_id_in_its_data():
    body = json.dumps({"cid": "cid-1", "type": "taskRequested", "data": {}})

    with pytest.raises(ValueError):
        TaskMessage.from_json(body)


def test_rejects_an_envelope_whose_data_is_not_an_object():
    body = json.dumps({"cid": "cid-1", "type": "taskRequested", "data": "t-42"})

    with pytest.raises(ValueError):
        TaskMessage.from_json(body)


def test_rejects_a_body_that_is_not_json():
    with pytest.raises(ValueError):
        TaskMessage.from_json("not json")


def test_rejects_a_json_body_that_is_not_an_object():
    with pytest.raises(ValueError):
        TaskMessage.from_json("[]")
