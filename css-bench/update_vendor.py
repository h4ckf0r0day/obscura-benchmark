#!/usr/bin/env python3
"""Verify or explicitly refresh the pinned production CSS corpus."""

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = HERE / "vendor.lock.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "obscura-benchmark-vendor/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def artifact_bytes(entry: dict) -> bytes:
    payload = download(entry["url"])
    member = entry.get("archive_member")
    if not member:
        return payload
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"archive member missing: {member}")
        return extracted.read()


def verify(entry: dict) -> None:
    path = HERE / entry["path"]
    if not path.exists():
        raise RuntimeError(f"missing {path}; run update_vendor.py --refresh")
    data = path.read_bytes()
    if len(data) != entry["bytes"]:
        raise RuntimeError(f"{entry['name']}: expected {entry['bytes']} bytes, got {len(data)}")
    digest = sha256(data)
    if digest != entry["sha256"]:
        raise RuntimeError(f"{entry['name']}: sha256 mismatch: {digest}")
    if not (HERE / entry["license_path"]).exists():
        raise RuntimeError(f"{entry['name']}: license file missing")


def refresh(entry: dict) -> None:
    data = artifact_bytes(entry)
    digest = sha256(data)
    if len(data) != entry["bytes"] or digest != entry["sha256"]:
        raise RuntimeError(
            f"{entry['name']}: upstream bytes changed; update vendor.lock.json manually "
            f"after review (bytes={len(data)}, sha256={digest})"
        )
    path = HERE / entry["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    license_path = HERE / entry["license_path"]
    license_path.parent.mkdir(parents=True, exist_ok=True)
    license_path.write_bytes(download(entry["license_url"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="download exactly the locked artifacts")
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text())
    for entry in lock["artifacts"]:
        if args.refresh:
            refresh(entry)
        verify(entry)
        print(f"ok  {entry['name']} {entry['version']}  {entry['bytes']} bytes  {entry['sha256'][:12]}")


if __name__ == "__main__":
    main()
