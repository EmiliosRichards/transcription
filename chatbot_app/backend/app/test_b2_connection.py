import os
import boto3
import boto3.session
from botocore.exceptions import ClientError
from dotenv import load_dotenv, find_dotenv


DEFAULT_EU_ENDPOINT = "https://s3.eu-central-003.backblazeb2.com"


def _derive_region_from_endpoint(endpoint_url: str | None) -> str | None:
    if not endpoint_url:
        return None
    try:
        host = endpoint_url.split("//", 1)[-1]
        parts = host.split(".")
        # e.g. s3.eu-central-003.backblazeb2.com -> eu-central-003
        return parts[1] if len(parts) > 1 else None
    except Exception:
        return None


def test_b2_connection_env_first():
    """
    Try B2 connection using environment variables (and .env),
    falling back to the named profile 'b2tutorial' if needed.
    """
    print("--- Starting B2 Connection Test ---")

    # Load .env if present anywhere up the tree
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
        print(f"Loaded .env from: {dotenv_path}")

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", DEFAULT_EU_ENDPOINT)
    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    region_name = _derive_region_from_endpoint(endpoint_url) or os.environ.get("AWS_REGION")

    print(f"Endpoint URL: {endpoint_url}")
    print(f"Region: {region_name}")

    # 1) Try explicit env credentials
    if access_key and secret_key:
        print("Attempting connection with environment credentials...")
        try:
            s3_client = boto3.client(
                service_name="s3",
                endpoint_url=endpoint_url,
                region_name=region_name,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
            )
            response = s3_client.list_buckets()
            print("\n[SUCCESS] Connection successful (env credentials)!")
            print("Buckets found in your account:")
            for bucket in response.get("Buckets", []):
                print(f"  - {bucket['Name']}")
            print("\n--- Test Complete ---")
            return
        except ClientError as e:
            print("[INFO] Env credential attempt failed, will try profile. Details:")
            print(f"  - Error Code: {e.response.get('Error', {}).get('Code')}")
            print(f"  - Error Message: {e.response.get('Error', {}).get('Message')}")
        except Exception as e:
            print(f"[INFO] Env credential attempt had an unexpected error: {e}. Will try profile next.")

    # 2) Fallback to named profile
    try:
        print("Attempting connection with profile 'b2tutorial'...")
        b2session = boto3.session.Session(profile_name="b2tutorial")
        s3_client = b2session.client("s3", endpoint_url=endpoint_url, region_name=region_name)
        response = s3_client.list_buckets()
        print("\n[SUCCESS] Connection successful (profile 'b2tutorial')!")
        print("Buckets found in your account:")
        for bucket in response.get("Buckets", []):
            print(f"  - {bucket['Name']}")
    except ClientError as e:
        print(f"\n[FAILED] Connection failed with a client error.")
        print(f"Error Code: {e.response['Error']['Code']}")
        print(f"Error Message: {e.response['Error']['Message']}")
        print("This error is coming directly from the Backblaze B2 service.")
        print("Please double-check your credentials and endpoint.")
    except Exception as e:
        print(f"\n[FAILED] An unexpected error occurred: {e}")
        print("This might indicate the 'b2tutorial' profile was not found or misconfigured.")

    print("\n--- Test Complete ---")


if __name__ == "__main__":
    test_b2_connection_env_first()