#!/usr/bin/env python3
"""Submit a file to the Talky hackathon and wait for the result (script published at hackathon.usetalky.com/enviar).

Usage:  read -rs HK_TOKEN && export HK_TOKEN
        uv run --with requests scripts/submit.py LIVE runs/<run>/submission.csv.gz

Only a person runs this: every call to upload-url consumes one of the daily slots. The token lives in HK_TOKEN only.
"""
import json
import os
import sys
import time

import requests

API = "https://hackathon.usetalky.com/api"
FINAL = {"scored", "received", "invalid", "error"}


def main(phase: str, path: str) -> None:
    headers = {"Authorization": f"Bearer {os.environ['HK_TOKEN']}"}
    name = os.path.basename(path)

    # 1) Reserve a slot and get the presigned S3 upload
    r = requests.post(f"{API}/submissions/upload-url", headers=headers,
                      json={"phase": phase, "filename": name}, timeout=30)
    if r.status_code != 201:
        sys.exit(f"upload-url failed: {r.status_code} {r.text}")
    up = r.json()
    sub_id = up["sub_id"]

    # 2) Upload to S3 (requests sends the form fields first, then the file)
    with open(path, "rb") as f:
        s3 = requests.post(up["upload"]["url"], data=up["upload"]["fields"],
                           files={"file": (name, f)}, timeout=900)
    if s3.status_code not in (200, 201, 204):
        sys.exit(f"S3 upload failed: {s3.status_code} {s3.text[:500]}")

    # 3) Queue scoring
    r = requests.post(f"{API}/submissions/{sub_id}/score", headers=headers, json={}, timeout=30)
    if r.status_code >= 400:
        sys.exit(f"score failed: {r.status_code} {r.text}")

    # 4) Poll every 5 s (the whole venue shares one IP), up to 10 min
    sub = r.json()
    deadline = time.time() + 600
    while sub.get("status") not in FINAL and time.time() < deadline:
        time.sleep(5)
        sub = requests.get(f"{API}/submissions/{sub_id}", headers=headers, timeout=30).json()

    print(json.dumps(sub, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("LIVE", "FINAL"):
        sys.exit("usage: python submit.py LIVE|FINAL file.csv[.gz]  (with HK_TOKEN exported)")
    main(sys.argv[1], sys.argv[2])
