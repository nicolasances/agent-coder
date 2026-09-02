"""GCP Secret Manager access.

Deliberately not behind a provider-agnostic seam: this repo resists adding
extension points beyond Harness and EventSink until a second provider
actually shows up (see docs/concept.md §3.6). Named `gcp_secrets`, not
`secrets`, so that non-portability is honest rather than implied away.
"""

import os

from google.cloud import secretmanager


def get_secret(project_id: str, secret_id: str, version_id: str = "latest") -> str:
    """Fetch and decode one secret version from GCP Secret Manager."""

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"

    response = client.access_secret_version(request={"name": name})

    return response.payload.data.decode("UTF-8")


def get_claude_oauth_token() -> str:
    """Fetch the Claude Code OAuth token from Secret Manager.

    Project id comes from the GCP_PID env var; the secret is named
    'claude_token'.
    """

    project_id = os.environ.get("GCP_PID")
    if not project_id:
        raise RuntimeError("GCP_PID environment variable is not set")

    return get_secret(project_id, "claude_token")
