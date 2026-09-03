

import json

from .harness import Harness


class Claude(Harness): 
    
    def get_secrets_names(self) -> list[str]: 
        return [
            "claude-token", # The name of the secret in GCP Secret Manager that contains the Claude Code OAuth token.
        ]

    def get_llm_message(self, stdout_line: str) -> str:
        # The line is usually json, but not guaranteed — a stray warning or a
        # line truncated by process exit shouldn't take the whole run down.
        try:
            structured_output = json.loads(stdout_line)
        except json.JSONDecodeError:
            return ""

        if structured_output.get("type") != "assistant":
            return ""

        content = (structured_output.get("message") or {}).get("content") or []

        # A single assistant event can carry several content blocks (e.g. a
        # thinking block followed by one or more tool calls) — render all of
        # them, not just the first, or most of a real run goes silent.
        lines = []

        for block in content:
            block_type = block.get("type")

            if block_type in ["thinking", "text"]:
                text = block.get(block_type)
                if text:
                    lines.append(text)
            elif block_type == "tool_use":
                lines.append(f"[tool] {block.get('name', 'tool')}({block.get('input', {})})")

        return "\n".join(lines)

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

