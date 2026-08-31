from typing import Protocol

class Harness(Protocol): 
    
    def build_command(self, prompt: str, model: str, permission_mode: str) -> list[str]: 
        ...
        