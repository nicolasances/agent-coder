from unittest.mock import patch

import pytest

from runner.skills import SKILLS_REPO, SkillsInstallError, install_skills


class FakeCompleted:
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


def test_install_skills_runs_npx_skills_add_globally_for_the_skills_repo():
    with patch("runner.skills.subprocess.run", return_value=FakeCompleted(0)) as mock_run:
        install_skills()

    assert mock_run.call_args.args[0] == ["npx", "skills", "add", SKILLS_REPO, "--global", "-y"]


def test_install_skills_raises_when_the_install_exits_non_zero():
    with patch("runner.skills.subprocess.run", return_value=FakeCompleted(1, "network unreachable")):
        with pytest.raises(SkillsInstallError, match="network unreachable"):
            install_skills()


def test_install_skills_raises_when_npx_is_not_available():
    with patch("runner.skills.subprocess.run", side_effect=FileNotFoundError("npx")):
        with pytest.raises(SkillsInstallError):
            install_skills()
