"""CI smoke test for real SMTP and S3-compatible protocol boundaries."""

import os
import time
import urllib.request
import uuid
import boto3
from botocore.config import Config
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend


def wait_for(url: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Provider did not become ready: {url}")


def smoke_s3() -> None:
    endpoint = os.environ.get("SMOKE_S3_ENDPOINT", "http://127.0.0.1:9000")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id="starter-access",
        aws_secret_access_key="starter-secret",
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    bucket = "starter-smoke"
    key = f"smoke/{uuid.uuid4().hex}.txt"
    client.create_bucket(Bucket=bucket)
    client.put_object(Bucket=bucket, Key=key, Body=b"provider-smoke")
    assert client.get_object(Bucket=bucket, Key=key)["Body"].read() == b"provider-smoke"
    client.delete_object(Bucket=bucket, Key=key)
    client.delete_bucket(Bucket=bucket)


def smoke_smtp() -> None:
    marker = f"provider-smoke-{uuid.uuid4().hex}"
    backend = EmailBackend(
        host="127.0.0.1",
        port=1025,
        username="",
        password="",
        use_tls=False,
        use_ssl=False,
        timeout=5,
    )
    message = EmailMessage(
        subject=marker,
        body="SMTP provider smoke test",
        from_email="starter@example.test",
        to=["recipient@example.test"],
        connection=backend,
    )
    assert message.send() == 1

    for _ in range(20):
        with urllib.request.urlopen(
            "http://127.0.0.1:8025/api/v1/messages"
        ) as response:
            if marker.encode() in response.read():
                return
        time.sleep(0.25)
    raise RuntimeError("Mailpit did not capture the SMTP message")


if __name__ == "__main__":
    wait_for("http://127.0.0.1:9000/minio/health/live")
    wait_for("http://127.0.0.1:8025/livez")
    smoke_s3()
    smoke_smtp()
