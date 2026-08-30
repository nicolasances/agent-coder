import subprocess

def main() -> int: 
    
    cmd = ["ls", "-l"]
    
    try: 
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        print(result.stdout)
        
        return 0
    
    except subprocess.CalledProcessError as e:
        print(f"Command '{' '.join(cmd)}' failed with exit code {e.returncode}")
        print(f"Error output: {e.stderr}")
        return e.returncode
    

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)