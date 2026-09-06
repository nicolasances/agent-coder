from unittest.mock import patch

from runner.harness.harness import Harness, HarnessInit
from runner.model.task import TaskSpec


class FakeStdout:
    def __init__(self, lines: list[str]):
        self._lines = lines

    def __enter__(self) -> "FakeStdout":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def __iter__(self):
        return iter(self._lines)


class FakeProc:
    def __init__(self, lines: list[str], exit_code: int = 0):
        self.stdout = FakeStdout(lines)
        self._exit_code = exit_code

    def wait(self) -> int:
        return self._exit_code


class RecordingHarness(Harness):
    """A minimal concrete Harness that records the prompt it was handed."""

    def __init__(self):
        super().__init__()
        self.received_prompt: str | None = None

    def get_secrets_names(self) -> list[str]:
        return []

    def get_llm_message(self, stdout_line: str) -> str:
        return ""

    def build_env(self, secrets: dict) -> dict:
        return {}

    def build_command(self, prompt: str, model: str | None) -> list[str]:
        self.received_prompt = prompt

        return ["fake-cli", prompt]


def a_task(issue_url: str = "https://github.com/acme/widgets/issues/7") -> TaskSpec:
    return TaskSpec(task_id="t-1", repo_url="https://github.com/acme/widgets.git", issue_url=issue_url)


def an_initialized_harness() -> RecordingHarness:
    with patch("runner.harness.harness.get_secret", return_value="tok-123"), patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        return RecordingHarness().initialize(HarnessInit(agent_data_bucket="a-bucket", trace_object_path="coder/t-1/trace.json"))  # type: ignore[return-value]


def test_run_task_builds_the_fixed_implement_issue_prompt_from_the_issue_url():
    harness = an_initialized_harness()

    with patch("runner.harness.harness.subprocess.Popen", return_value=FakeProc([])), patch("runner.harness.harness.put_object"):
        harness.run_task(a_task("https://github.com/acme/widgets/issues/7"))

    assert harness.received_prompt == "/implement issue https://github.com/acme/widgets/issues/7"


def test_run_task_prompt_varies_only_by_the_issue_url():
    harness = an_initialized_harness()

    with patch("runner.harness.harness.subprocess.Popen", return_value=FakeProc([])), patch("runner.harness.harness.put_object"):
        harness.run_task(a_task("https://github.com/nicolasances/agent-coder/issues/5"))

    assert harness.received_prompt == "/implement issue https://github.com/nicolasances/agent-coder/issues/5"


def test_run_task_passes_the_built_prompt_through_to_the_launched_command():
    harness = an_initialized_harness()

    with patch("runner.harness.harness.subprocess.Popen", return_value=FakeProc([])) as mock_popen, patch("runner.harness.harness.put_object"):
        harness.run_task(a_task())

    assert mock_popen.call_args.args[0] == ["fake-cli", "/implement issue https://github.com/acme/widgets/issues/7"]


def test_run_task_returns_the_subprocess_exit_code():
    harness = an_initialized_harness()

    with patch("runner.harness.harness.subprocess.Popen", return_value=FakeProc([], exit_code=20)), patch("runner.harness.harness.put_object"):
        exit_code = harness.run_task(a_task())

    assert exit_code == 20
