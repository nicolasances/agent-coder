

from harness.harness import Harness


class Claude(Harness): 
    
    def __init__(self): 
        pass 
    
    def build_command(self, prompt: str, model: str = "sonnet", permission_mode: str = "acceptEdits"): 
        
        cmd = [
            "claude", 
            "-p", 
            prompt, 
            "--model", model,
            # "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", permission_mode
        ]
        
        return cmd
