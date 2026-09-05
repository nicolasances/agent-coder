
import subprocess


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