

import json

from runner.config.runner import RunnerConfig

from .harness import Harness


class Claude(Harness): 
    
    def __init__(self, runner_config: RunnerConfig): 
        super().__init__(runner_config)

    def get_secrets_names(self) -> list[str]: 
        return [
            "claude-token", # The name of the secret in GCP Secret Manager that contains the Claude Code OAuth token.
        ]

    def get_llm_message(self, stdout_line: str) -> str:
        # The line is a json. Let's parse it.
        structured_output = json.loads(stdout_line) 

        if structured_output.get("type") == "assistant": 
            if "message" in structured_output and "content" in structured_output.get("message") and structured_output.get("message"): 
                msg = structured_output.get("message").get("content")[0]

                if msg.get("type") in ["thinking", "text"]: 
                    return msg.get(msg.get("type"))

        return ""

    def build_env(self, secrets: dict) -> dict:
        # Build the environment variables needed to run the harness command.
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN": secrets.get("claude-token", ""),
        }

        return env  
    
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

