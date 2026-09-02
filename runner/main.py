import json
import os
import subprocess

from .harness.claude import Claude
from .gcp_secrets import get_claude_oauth_token

def main() -> int:

    try:

        oauth_token = get_claude_oauth_token()

    except Exception as e:
        # Can't reach Secret Manager / no token -> infra failure, not a task
        # failure (see docs/concept.md §4.5). No exit-code taxonomy wired up
        # yet, so this is a plain non-zero for now.
        print(f"Failed to fetch Claude OAuth token from Secret Manager: {e}")
        return 30

    # ANTHROPIC_API_KEY outranks CLAUDE_CODE_OAUTH_TOKEN in Claude Code's
    # auth precedence. If it's set in the environment it will silently win,
    # so guard against that rather than have the token be quietly ignored.
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is set; it takes precedence over CLAUDE_CODE_OAUTH_TOKEN and must be unset to use the subscription token.")
        return 30

    cmd = Claude().build_command("Describe what you think this repo is about", model="haiku")

    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": oauth_token}

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        
        with proc.stdout as stdout: # type: ignore
            
            for line in stdout:
                
                # The line is a json. Let's parse it.
                structured_output = json.loads(line) 

                if structured_output.get("type") == "assistant": 
                    if "message" in structured_output and "content" in structured_output.get("message") and structured_output.get("message"): 
                        msg = structured_output.get("message").get("content")[0]
                        
                        if msg.get("type") in ["thinking", "text"]: 
                            print(msg.get(msg.get("type")))
                
        return proc.wait()
    
    except subprocess.CalledProcessError as e:
        print(f"Command '{' '.join(cmd)}' failed with exit code {e.returncode}")
        print(f"Error output: {e.stderr}")
        return e.returncode
    

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)