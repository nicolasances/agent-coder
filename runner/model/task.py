import json

class Task: 
    """ 
    Models the Task that a Coding Agent can receive.
    """

    prompt: str # The prompt that defines what this agent needs to do.

    def __init__(self, task_json_file: str) -> None: 

        # Parse the JSON file to get the task details
        with open(task_json_file, 'r') as f:

            task_details = json.load(f)

            if "prompt" not in task_details:
                raise ValueError("The task JSON file must contain a 'prompt' field.")

            self.prompt = task_details["prompt"]
