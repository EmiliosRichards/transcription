"""
B2 Bucket Cleanup Script — campaign-analysis
=============================================
Identifies and optionally deletes stale/orphan files from the B2 bucket.

Usage:
    python b2_cleanup.py                 # Dry run — shows what would be deleted
    python b2_cleanup.py --execute       # Actually deletes files
    python b2_cleanup.py --section root  # Only process a specific section

Sections:
    root              — 7 orphan PR_*.mp3 files + 1 meeting MP4 at bucket root
    benchmarks        — benchmarks_mixed/ folder (3.5 MB, stale since Sep 2025)
    unspecified       — unspecified/ folder (599 KB, test data)
    dual_campaign     — manuav-dual-campaign/ folder (179 MB, stale since Sep 2025)
    dexter_txt        — dexter/transcriptions/txt/ (97.6K files, ~300 MB, duplicates JSON)
"""

import argparse
import os
import sys
import boto3

BUCKET = os.environ.get("BACKBLAZE_B2_BUCKET", "campaign-analysis")
ENDPOINT = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")
KEY_ID = os.environ.get("BACKBLAZE_B2_KEY_ID", "")
APP_KEY = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY", "")


def get_client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=KEY_ID,
        aws_secret_access_key=APP_KEY,
    )


def list_objects(client, prefix="", delimiter=""):
    """List all objects under a prefix."""
    objects = []
    kwargs = {"Bucket": BUCKET, "Prefix": prefix}
    if delimiter:
        kwargs["Delimiter"] = delimiter
    while True:
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            objects.append(obj)
        if not resp.get("IsTruncated"):
            break
        kwargs["ContinuationToken"] = resp["NextContinuationToken"]
    return objects


def human_size(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def delete_objects(client, keys, execute=False, batch_size=1000):
    """Delete objects in batches of 1000 (S3 API limit)."""
    deleted = 0
    for i in range(0, len(keys), batch_size):
        batch = keys[i : i + batch_size]
        if execute:
            client.delete_objects(
                Bucket=BUCKET,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
        deleted += len(batch)
        if execute:
            print(f"  Deleted {deleted}/{len(keys)} objects...")
    return deleted


def section_root(client, execute):
    """Root-level orphan files (PR_*.mp3 + meeting MP4)."""
    print("\n=== ROOT ORPHANS ===")
    all_root = list_objects(client, prefix="")
    # Only files at root level (no / in key, or just the key itself)
    orphans = [obj for obj in all_root if "/" not in obj["Key"]]

    if not orphans:
        print("  No root-level files found.")
        return

    total_size = sum(o["Size"] for o in orphans)
    print(f"  Found {len(orphans)} files ({human_size(total_size)}):")
    for obj in orphans:
        print(f"    {obj['Key']:60s}  {human_size(obj['Size']):>10s}  {obj['LastModified'].strftime('%Y-%m-%d')}")

    if execute:
        confirm = input(f"\n  Delete these {len(orphans)} root files? [y/N]: ")
        if confirm.lower() == "y":
            delete_objects(client, [o["Key"] for o in orphans], execute=True)
            print(f"  Deleted {len(orphans)} files ({human_size(total_size)})")
        else:
            print("  Skipped.")
    else:
        print(f"\n  DRY RUN — would delete {len(orphans)} files ({human_size(total_size)})")


def section_prefix(client, execute, prefix, label):
    """Generic section for deleting an entire prefix."""
    print(f"\n=== {label} ===")
    objects = list_objects(client, prefix=prefix)

    if not objects:
        print(f"  No files found under {prefix}")
        return

    total_size = sum(o["Size"] for o in objects)
    print(f"  Found {len(objects)} files ({human_size(total_size)})")
    print(f"  Date range: {min(o['LastModified'] for o in objects).strftime('%Y-%m-%d')} — {max(o['LastModified'] for o in objects).strftime('%Y-%m-%d')}")

    # Show a sample of files
    sample = objects[:5]
    for obj in sample:
        print(f"    {obj['Key'][:80]:80s}  {human_size(obj['Size']):>10s}")
    if len(objects) > 5:
        print(f"    ... and {len(objects) - 5} more")

    if execute:
        confirm = input(f"\n  Delete ALL {len(objects)} files under {prefix}? [y/N]: ")
        if confirm.lower() == "y":
            delete_objects(client, [o["Key"] for o in objects], execute=True)
            print(f"  Deleted {len(objects)} files ({human_size(total_size)})")
        else:
            print("  Skipped.")
    else:
        print(f"\n  DRY RUN — would delete {len(objects)} files ({human_size(total_size)})")


def main():
    parser = argparse.ArgumentParser(description="B2 bucket cleanup for campaign-analysis")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (default is dry run)")
    parser.add_argument("--section", choices=["root", "benchmarks", "unspecified", "dual_campaign", "dexter_txt", "all"], default="all", help="Which section to process")
    args = parser.parse_args()

    if not KEY_ID or not APP_KEY:
        print("Error: Set BACKBLAZE_B2_KEY_ID and BACKBLAZE_B2_APPLICATION_KEY env vars (or use .env)")
        sys.exit(1)

    client = get_client()

    if args.execute:
        print("*** EXECUTE MODE — files will be permanently deleted ***\n")
    else:
        print("*** DRY RUN — no files will be deleted (use --execute to delete) ***\n")

    sections = {
        "root": lambda: section_root(client, args.execute),
        "benchmarks": lambda: section_prefix(client, args.execute, "benchmarks_mixed/", "BENCHMARKS_MIXED (stale since Sep 2025)"),
        "unspecified": lambda: section_prefix(client, args.execute, "unspecified/", "UNSPECIFIED (test data)"),
        "dual_campaign": lambda: section_prefix(client, args.execute, "manuav-dual-campaign/", "MANUAV-DUAL-CAMPAIGN (stale since Sep 2025)"),
        "dexter_txt": lambda: section_prefix(client, args.execute, "dexter/transcriptions/txt/", "DEXTER TXT TRANSCRIPTS (duplicates JSON)"),
    }

    if args.section == "all":
        for fn in sections.values():
            fn()
    else:
        sections[args.section]()

    print("\nDone.")


if __name__ == "__main__":
    main()
