from abc import ABC, abstractmethod
import json
import os
import subprocess

from runner.gcp_storage import put_object
from runner.model.task import TaskSpec
from runner.gcp_secrets import get_secret

SECRET_NAME_CODING_AGENT_GH_TOKEN = "coding-agent-gh-token"

class HarnessInit: 
    def __init__(self, agent_data_bucket: str, trace_object_path: str): 
        self.agent_data_bucket = agent_data_bucket
        self.trace_object_path = trace_object_path

class Harness(ABC):

    initialized: bool = False
    harness_config: HarnessInit
    base_secrets = [
        SECRET_NAME_CODING_AGENT_GH_TOKEN
    ]

    def __init__(self, model: str | None = None): 
        self.model = model

    def set_secrets(self, secrets: dict): 
        self.secrets = secrets

    @abstractmethod
    def get_secrets_names(self) -> list[str]:
        """Return a list of secret names that this harness needs to function.

        An example of secret name is the "claude_token" needed by the harness. 
        Each harness defines its own secret names, and the runner will fetch them from the configured secret manager (e.g., GCP Secret Manager) and provide them to the harness.
        """
        ...
    
    @abstractmethod
    def build_command(self, prompt: str, model: str | None) -> list[str]: 
        ...

    @abstractmethod
    def get_llm_message(self, stdout_line: str) -> str:
        ...

    @abstractmethod
    def build_env(self, secrets: dict) -> dict:
        """Build the environment variables needed to run the harness command.

        This method takes a dictionary of secrets (fetched from the secret manager) and returns a dictionary of environment variables that will be used when running the harness command.
        """
        ...

    def initialize(self, harness_init: HarnessInit) -> "Harness":
        """Perform any necessary initialization for the harness.

        By default, it loads the secrets that this harness needs. 
        This method can be overridden by subclasses to perform any setup or initialization required before running the harness command. 
        """
        project_id = os.environ.get("GCP_PID")

        secrets = {}

        harness_secrets_names = self.get_secrets_names() + self.base_secrets

        # 1. Load secrets from GCP Secrets Manager
        # Parallelize the fetching of secrets from GCP Secret Manager for efficiency.
        for secret_name in harness_secrets_names: 

            try: 
                secret_value = get_secret(project_id, secret_name)  # type: ignore
                secrets[secret_name] = secret_value

                print(f"Loaded secret '{secret_name}' from GCP Secret Manager.")

            except Exception as e:
                print(f"Failed to fetch secret '{secret_name}' from GCP Secret Manager: {e}")
                raise e

        self.set_secrets(secrets)
        self.harness_config = harness_init
        self.initialized = True

        return self
    
    def run_task(self, task: TaskSpec, workdir: str | None = None) -> int:
        """Run the task in a subprocess, streaming output to stdout and
        collecting every raw stdout line into a trace.

        workdir is where the harness CLI actually operates — the freshly
        cloned repo (GitOps.local_path), not this process's own cwd. Passed
        straight through to subprocess.Popen's cwd, which is what decides a
        CLI's project root; it's scoped to the child process only, so this
        runner's own working directory is never touched. Left as None for
        callers with no repo to operate on (e.g. tests), matching Popen's own
        default of inheriting the caller's cwd.

        If trace_bucket and trace_object are given, the trace is uploaded to
        GCS as a JSON array once the process exits. Writing the trace is
        best-effort: a failure to write it is logged but never changes the
        run's exit code — losing the trace is not the same kind of failure as
        losing the actual work.
        """

        if not self.initialized:
            raise ValueError("Harness has not been initialized. Please call initialize() before running the command.")

        # General env vars, harness-agnostic
        agnostic_env = {
            "GH_TOKEN": self.secrets[SECRET_NAME_CODING_AGENT_GH_TOKEN],
        }

        env = {**os.environ, **self.build_env(self.secrets), **agnostic_env}

        # Build the command to run the harness.
        # This is specific to the chosen harness implementation (e.g., Claude, GPT, etc.) and is defined in the subclass.
        command = self.build_command(task.prompt, self.model)

        trace: list = []

        try:
            # Start the process
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=workdir)

            with proc.stdout as stdout: # type: ignore

                for line in stdout:
                    trace.append(self._trace_entry(line))

                    msg = self.get_llm_message(line)
                    if msg:
                        print(msg, flush=True)

            exit_code = proc.wait()

        except subprocess.CalledProcessError as e:
            print(f"Command '{' '.join(command)}' failed with exit code {e.returncode}")
            print(f"Error output: {e.stderr}")
            exit_code = e.returncode

        # Write the trace to the target bucket
        self._write_trace(trace, self.harness_config.agent_data_bucket, self.harness_config.trace_object_path)

        return exit_code

    @staticmethod
    def _trace_entry(stdout_line: str) -> dict:
        """Parse one raw stdout line for the trace, without ever losing it."""

        stripped = stdout_line.rstrip("\n")

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return {"raw": stripped}

    @staticmethod
    def _write_trace(trace: list, bucket: str | None, object_name: str | None) -> None:
        if not bucket or not object_name:
            return

        try:
            put_object(bucket, object_name, json.dumps(trace))
        except Exception as e:
            print(f"Failed to write trace to gs://{bucket}/{object_name}: {e}")