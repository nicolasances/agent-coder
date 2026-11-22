import subprocess

# The Skill Pack the agent works with. Installed from the repo's default branch at every
# container start, so a change pushed there reaches the next run without an image rebuild
# (docs/concept.md §3.5).
SKILLS_REPO = "nicolasances/skills-coding"

class SkillsInstallError(RuntimeError):
    """The Skill Pack could not be installed. Maps to exit code 30 (infra failure, retryable)."""

def install_skills() -> None:

    # --global: skills apply to whichever repo gets cloned into /workspace, not to the
    # directory the runner happens to be started in. Runs as the `agent` user, so it lands in its HOME.
    try:
        result = subprocess.run(["npx", "skills", "add", SKILLS_REPO, "--global", "-y"], capture_output=True, text=True)
    except FileNotFoundError as e:
        raise SkillsInstallError(f"Could not run npx to install skills from {SKILLS_REPO}: {e}") from e

    if result.returncode != 0:
        raise SkillsInstallError(f"Failed to install skills from {SKILLS_REPO}. Exit code: {result.returncode}. {result.stderr}")

    print(f"Successfully installed skills from {SKILLS_REPO}")
