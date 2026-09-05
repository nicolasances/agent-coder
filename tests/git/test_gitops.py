from unittest.mock import patch

import pytest

from runner.git.gitops import GitOps


class FakeProc:
    def __init__(self, exit_code: int):
        self._exit_code = exit_code

    def wait(self) -> int:
        return self._exit_code


def test_push_branch_fetches_token_from_secret_manager_using_gcp_pid():
    with patch("runner.git.gitops.get_secret", return_value="tok-123") as mock_get_secret, patch("runner.git.gitops.subprocess.Popen", return_value=FakeProc(0)), patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")
        git_ops.local_path = "/workspace"

        git_ops.push_branch()

    mock_get_secret.assert_called_once_with("my-project", "github-token")


def test_push_branch_invokes_git_push_with_authenticated_url_and_branch():
    with patch("runner.git.gitops.get_secret", return_value="tok-123"), patch("runner.git.gitops.subprocess.Popen", return_value=FakeProc(0)) as mock_popen, patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")
        git_ops.local_path = "/workspace"

        git_ops.push_branch()

    command = mock_popen.call_args.args[0]

    assert command[0] == "git"
    assert command[1] == "push"
    assert "https://x-access-token:tok-123@github.com/acme/widgets" in command
    assert "agent/t-1" in command


def test_push_branch_runs_from_the_cloned_repos_directory():
    with patch("runner.git.gitops.get_secret", return_value="tok-123"), patch("runner.git.gitops.subprocess.Popen", return_value=FakeProc(0)) as mock_popen, patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")
        git_ops.local_path = "/workspace"

        git_ops.push_branch()

    assert mock_popen.call_args.kwargs["cwd"] == "/workspace"


def test_push_branch_never_writes_the_token_to_git_config():
    # The token must only ever appear as a one-off push argument, never
    # persisted via `git remote set-url` (which would leave it on disk in
    # the cloned workspace).
    with patch("runner.git.gitops.get_secret", return_value="tok-123"), patch("runner.git.gitops.subprocess.Popen", return_value=FakeProc(0)) as mock_popen, patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")
        git_ops.local_path = "/workspace"

        git_ops.push_branch()

    command = mock_popen.call_args.args[0]

    assert "remote" not in command
    assert "set-url" not in command


def test_push_branch_raises_on_non_zero_exit_code():
    with patch("runner.git.gitops.get_secret", return_value="tok-123"), patch("runner.git.gitops.subprocess.Popen", return_value=FakeProc(1)), patch.dict("os.environ", {"GCP_PID": "my-project"}, clear=False):
        git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")
        git_ops.local_path = "/workspace"

        with pytest.raises(RuntimeError):
            git_ops.push_branch()


def test_push_branch_raises_if_repo_was_never_cloned():
    git_ops = GitOps(repoURL="https://github.com/acme/widgets", branch="agent/t-1")

    with pytest.raises(RuntimeError):
        git_ops.push_branch()
