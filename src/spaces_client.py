"""Shared DigitalOcean Spaces (S3-compatible) helpers."""

from __future__ import annotations

import logging

import boto3

log = logging.getLogger("spaces_client")


def make_spaces_client(cfg):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg.spaces_region}.digitaloceanspaces.com",
        aws_access_key_id=cfg.spaces_access_key_id,
        aws_secret_access_key=cfg.spaces_secret_access_key,
        region_name=cfg.spaces_region,
    )


def put_text_object(cfg, key: str, body: str, content_type: str = "text/plain") -> None:
    client = make_spaces_client(cfg)
    client.put_object(
        Bucket=cfg.spaces_bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType=content_type,
    )
    log.info("Uploaded to Spaces — s3://%s/%s (%d bytes)", cfg.spaces_bucket, key, len(body))
