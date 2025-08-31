import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv, find_dotenv


def main() -> None:
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
        print(f"Loaded .env from: {dotenv_path}")

    endpoint = os.environ.get("BACKBLAZE_B2_S3_ENDPOINT") or os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("BACKBLAZE_B2_REGION") or os.environ.get("AWS_REGION")
    bucket = os.environ.get("BACKBLAZE_B2_BUCKET") or os.environ.get("B2_BUCKET_NAME")
    key_id = os.environ.get("BACKBLAZE_B2_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    app_key = os.environ.get("BACKBLAZE_B2_APPLICATION_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")

    print("\n--- Config ---")
    print(f"Endpoint: {endpoint}")
    print(f"Region:   {region}")
    print(f"Bucket:   {bucket}")
    print(f"Key ID:   ...{key_id[-6:] if key_id else None}")
    print(f"AppKey len: {len(app_key) if app_key else None}")

    if not (endpoint and region and bucket and key_id and app_key):
        print("Missing required env vars. Ensure BACKBLAZE_* values are set.")
        return

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=app_key,
    )

    # 1) Bucket reachability (head_bucket)
    try:
        s3.head_bucket(Bucket=bucket)
        print("head_bucket: OK")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        print(f"head_bucket error: {code} - {e.response.get('Error', {}).get('Message')}")

    # 2) List a single object (less privilege than ListAllMyBuckets)
    try:
        resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
        count = resp.get("KeyCount", 0)
        print(f"list_objects_v2: OK (KeyCount={count})")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        print(f"list_objects_v2 error: {code} - {e.response.get('Error', {}).get('Message')}")

    print("\nDone.")


if __name__ == "__main__":
    main()


