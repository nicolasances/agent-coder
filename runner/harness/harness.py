from typing import Protocol

class Harness(Protocol): 

    def get_secrets_names(self) -> list[str]:
        """Return a list of secret names that this harness needs to function.

        An example of secret name is the "claude_token" needed by the harness. 
        Each harness defines its own secret names, and the runner will fetch them from the configured secret manager (e.g., GCP Secret Manager) and provide them to the harness.
        """
        ...
    
    def build_command(self, prompt: str, model: str, permission_mode: str) -> list[str]: 
        ...
        