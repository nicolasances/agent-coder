from unittest.mock import MagicMock, patch

from runner import main as runner_main
from runner.skills import SkillsInstallError


def test_main_exits_30_and_never_starts_the_agent_when_skills_install_fails():
    with patch.object(runner_main, "install_skills", side_effect=SkillsInstallError("boom")), patch.object(runner_main, "Claude") as mock_claude, patch.object(runner_main, "resolve_task") as mock_resolve_task, patch.object(runner_main, "GitOps") as mock_git_ops:
        exit_code = runner_main.main()

    assert exit_code == 30
    mock_claude.assert_not_called()
    mock_resolve_task.assert_not_called()
    mock_git_ops.assert_not_called()


def test_main_installs_skills_before_running_the_harness():
    calls = []
    harness = MagicMock()
    harness.run_task.side_effect = lambda *a, **k: calls.append("run_task") or 0

    with patch.object(runner_main, "install_skills", side_effect=lambda: calls.append("install_skills")), patch.object(runner_main, "Claude") as mock_claude, patch.object(runner_main, "harness_init"), patch.object(runner_main, "resolve_task"), patch.object(runner_main, "GitOps"):
        mock_claude.return_value.initialize.return_value = harness

        exit_code = runner_main.main()

    assert exit_code == 0
    assert calls == ["install_skills", "run_task"]
