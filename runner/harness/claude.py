

from .harness import Harness


class Claude(Harness): 
    
    def __init__(self): 
        pass 

    def get_secrets_names(self) -> list[str]: 
        return [
            "claude_token", # The name of the secret in GCP Secret Manager that contains the Claude Code OAuth token.
        ]
    
    def build_command(self, prompt: str, model: str = "sonnet", permission_mode: str = "acceptEdits"): 
        
        cmd = [
            "claude", 
            "-p", 
            prompt, 
            "--model", model,
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", permission_mode
        ]
        
        return cmd

