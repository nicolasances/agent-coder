
import os
import subprocess

from runner.gcp_secrets import get_secret


TARGET_DIR = "/workspace"

class GitOps: 

    def __init__(self, repoURL: str, branch: str = "main"):

        self.repoURL = repoURL
        self.branch = branch
        self.local_path: str | None = None

    def clone_repo(self) -> None:

        # Clone the repository into the target directory
        proc = subprocess.Popen(["git", "clone", "--branch", self.branch, self.repoURL, TARGET_DIR], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        exit_code = proc.wait()

        if exit_code != 0:
            raise RuntimeError(f"Failed to clone repository {self.repoURL} on branch {self.branch}. Exit code: {exit_code}")
        else:
            self.local_path = TARGET_DIR
            print(f"Successfully cloned repository {self.repoURL} on branch {self.branch} into {TARGET_DIR}")

    def push_branch(self) -> None:

        if not self.local_path:
            raise RuntimeError("Cannot push: clone_repo() must succeed before push_branch() can run.")

        token = get_secret(os.environ.get("GCP_PID"), "github-token")
        authenticated_url = self.repoURL.replace("https://", f"https://x-access-token:{token}@", 1)

        # The token only ever appears as a one-off push argument, never persisted via
        # `git remote set-url` — it must not be written to .git/config on disk.
        proc = subprocess.Popen(["git", "push", authenticated_url, self.branch], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.local_path)

        exit_code = proc.wait()

        if exit_code != 0:
            raise RuntimeError(f"Failed to push branch {self.branch} to {self.repoURL}. Exit code: {exit_code}")
        else:
            print(f"Successfully pushed branch {self.branch} to {self.repoURL}")

    def create_pull_request(self, title: str, head: str, base: str, body: str = "") -> str:

        if not self.local_path:
            raise RuntimeError("Cannot open a pull request: clone_repo() must succeed before create_pull_request() can run.")

        token = get_secret(os.environ.get("GCP_PID"), "github-token")
        env = {**os.environ, "GH_TOKEN": token}

        # gh reads GH_TOKEN from the environment natively — no `gh auth login` needed,
        # and the token never touches disk.
        proc = subprocess.Popen(["gh", "pr", "create", "--title", title, "--body", body, "--head", head, "--base", base], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=self.local_path, env=env)
        stdout, stderr = proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create pull request for branch {head} into {base}. Exit code: {proc.returncode}. Error: {stderr}")

        return stdout.strip()