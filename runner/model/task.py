import json

class Task: 
    """ 
    Models the Task that a Coding Agent can receive.
    """

    prompt: str # The prompt that defines what this agent needs to do.

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt

    @staticmethod
    def from_json(task_json_file: str) -> 'Task':
        
        # Parse the JSON file to get the task details
        with open(task_json_file, 'r') as f:
            task_details = json.load(f)

        if "prompt" not in task_details:
            raise ValueError("The task JSON file must contain a 'prompt' field.")

        return Task(prompt=task_details["prompt"])

class CodingTask(Task): 

    repo: str # Repository that this coding task is referred to. Has to be a full URL to a GitHub repository.

    def __init__(self, prompt: str, repo: str) -> None:
        super().__init__(prompt)
        self.repo = repo

    @staticmethod
    def from_json(task_json_file: str) -> 'CodingTask':

        # Parse the JSON file to get the task details
        with open(task_json_file, 'r') as f:
            task_details = json.load(f)

        if "prompt" not in task_details or "repo" not in task_details:
            raise ValueError("The coding task JSON file must contain both 'prompt' and 'repo' fields.")

        return CodingTask(prompt=task_details["prompt"], repo=task_details["repo"])