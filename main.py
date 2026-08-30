import json
import subprocess

from harness.claude import Claude

def main() -> int: 
    
    cmd = Claude().build_command("Describe what you think this repo is about", model="haiku")
    
    try: 
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        with proc.stdout as stdout:
            
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