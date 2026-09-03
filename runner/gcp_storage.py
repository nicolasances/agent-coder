"""GCS access for Task Files and Result Files.

Deliberately not behind a provider-agnostic seam, for the same reason as
gcp_secrets.py (see docs/concept.md §3.6): this repo resists adding extension
points beyond Harness and EventSink until a second provider actually shows up.
"""

from google.cloud import storage


def get_object(bucket_name: str, object_name: str) -> str:
    """Fetch and decode one GCS object as text."""

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    return blob.download_as_text()


def put_object(bucket_name: str, object_name: str, content: str, content_type: str = "application/json") -> None:
    """Upload text content to a GCS object, overwriting any existing object at that name."""

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    blob.upload_from_string(content, content_type=content_type)
