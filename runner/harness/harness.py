from abc import ABC, abstractmethod
import os
import subprocess

class Harness(ABC): 

    def __init__(self): 
        pass

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
    def build_command(self, prompt: str, model: str, permission_mode: str) -> list[str]: 
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

    def run_command(self, command: list[str]) -> int: 
        """Run the command in a subprocess and stream the output to stdout."""

        if not hasattr(self, 'secrets'):
            raise ValueError("Secrets have not been set. Please call set_secrets() before running the command.")

        env = {**os.environ, **self.build_env(self.secrets)}

        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            
            with proc.stdout as stdout: # type: ignore

                for line in stdout:
                    msg = self.get_llm_message(line)
                    if msg:
                        print(msg, flush=True)


            return proc.wait()
        
        except subprocess.CalledProcessError as e:
            print(f"Command '{' '.join(command)}' failed with exit code {e.returncode}")
            print(f"Error output: {e.stderr}")
            return e.returncode