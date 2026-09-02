

import os

from runner.harness.harness import Harness
from runner.gcp_secrets import get_secret


class RunnerConfig: 

    secrets: dict = {}

    def __init__(self, secrets: dict = {}): 
        if secrets is not None:
            self.secrets = secrets

    @staticmethod
    def get_config(harness: Harness):

        project_id = os.environ.get("GCP_PID")

        secrets = {}

        harness_secrets_names = harness.get_secrets_names()

        # 1. Load secrets from GCP Secrets Manager
        # Parallelize the fetching of secrets from GCP Secret Manager for efficiency.
        for secret_name in harness_secrets_names: 
            secret_value = get_secret(project_id, secret_name)  # type: ignore
            secrets[secret_name] = secret_value

        # 2. Load secrets from environment variables

        # Return 
        return RunnerConfig(secrets=secrets)