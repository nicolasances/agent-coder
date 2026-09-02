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


