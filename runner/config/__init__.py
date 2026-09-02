
class RunnerConfig: 

    secrets: dict = {}

    def __init__(self, secrets: dict = {}): 
        if secrets is not None:
            self.secrets = secrets

    @staticmethod
    def get_config():

        secrets = {}

        # 1. Load secrets from GCP Secrets Manager


        # 2. Load secrets from environment variables

        # Return 