import os
import sys
import asyncio
import argparse
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# --- Path Correction ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database import Transcription, Base
from app.services.storage import StorageService

def parse_args():
    parser = argparse.ArgumentParser(description="Migrate local audio files to B2.")
    parser.add_argument("--db-url", required=True, help="Database connection URL.")
    return parser.parse_args()

async def migrate_audio_files(args):
    """
    Migrates local audio files to the B2 bucket and updates the database.
    """
    print("Starting audio file migration to B2...")

    # --- Load Environment Variables ---
    load_dotenv()
    b2_bucket = os.environ.get("B2_BUCKET_NAME")
    
    # Diagnostic logging for the bucket name
    print("\n--- DIAGNOSTIC: Checking Environment Variables ---")
    print(f"  - B2_BUCKET_NAME: {b2_bucket}")
    print("  - AWS credentials will be loaded automatically by Boto3.")
    print("------------------------------------------------\n")

    if not b2_bucket:
        print("Error: B2_BUCKET_NAME environment variable not set. Please check your .env file.")
        sys.exit(1)

    # --- Service Initialization ---
    # The StorageService now automatically uses the AWS_* environment variables.
    storage_service = StorageService(bucket_name=b2_bucket)

    # --- Database Setup ---
    db_url = args.db_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
    parsed_url = urlparse(db_url)
    query_params = parse_qs(parsed_url.query)
    
    connect_args = {}
    if 'sslmode' in query_params and query_params['sslmode'][0] == 'require':
        connect_args['ssl'] = 'require'

    db_url_without_query = parsed_url._replace(query=None).geturl()

    async_engine = create_async_engine(
        db_url_without_query,
        connect_args=connect_args,
        pool_pre_ping=True
    )
    
    AsyncSessionLocal = async_sessionmaker(bind=async_engine)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(Transcription).filter(Transcription.audio_file_path.like('%audio_files%'))
            result = await session.execute(stmt)
            transcriptions_to_migrate = result.scalars().all()

            if not transcriptions_to_migrate:
                print("No local audio files found to migrate. Database is up to date.")
                return

            print(f"Found {len(transcriptions_to_migrate)} audio files to migrate.")
            
            migrated_count = 0
            failed_count = 0

            for record in transcriptions_to_migrate:
                local_path = str(record.audio_file_path)
                object_key = os.path.basename(local_path)

                print(f"  - Migrating record ID {record.id}: {local_path}")

                if not os.path.exists(local_path):
                    print(f"    [!] WARNING: File not found at {local_path}. Skipping.")
                    failed_count += 1
                    continue

                print(f"    - Uploading to B2 with key: {object_key}...")
                upload_success = storage_service.upload_file(local_path, object_key)

                if upload_success:
                    record.audio_file_path = object_key # type: ignore
                    session.add(record)
                    print(f"    - Successfully uploaded for record {record.id}. DB will be updated.")
                    migrated_count += 1
                else:
                    print(f"    [!] ERROR: Failed to upload {local_path}. Skipping database update.")
                    failed_count += 1
            
            await session.commit()
            print("\nDatabase changes committed.")

    print("\n--- Migration Summary ---")
    print(f"Successfully migrated: {migrated_count}")
    print(f"Failed or skipped:    {failed_count}")
    print("-------------------------\n")

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(migrate_audio_files(args))