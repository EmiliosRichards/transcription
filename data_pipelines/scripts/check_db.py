import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import sys

# Adjust path to find the .env file in the backend directory
# This assumes the script is run from the root project directory
dotenv_path = os.path.join(os.path.dirname(__file__), '..', 'chatbot_poc', 'backend', '.env')
load_dotenv(dotenv_path=dotenv_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not found. Make sure the .env file is in the 'chatbot_poc/backend' directory.")
    sys.exit(1)

try:
    engine = create_engine(DATABASE_URL)
    with engine.connect() as connection:
        print("--- Successfully connected to the database. ---")
        
        print("\n--- Checking 'transcriptions' table... ---")
        transcriptions_query = text("SELECT id, created_at, audio_source FROM transcriptions ORDER BY created_at DESC LIMIT 10")
        transcriptions_result = connection.execute(transcriptions_query)
        transcriptions = transcriptions_result.fetchall()
        
        if transcriptions:
            print(f"Found {len(transcriptions)} transcription(s):")
            for row in transcriptions:
                print(f"  ID: {row[0]}, Created: {row[1]}, Source: {row[2]}")
        else:
            print("No records found in the 'transcriptions' table.")

        print("\n--- Checking 'chat_logs' table... ---")
        chat_logs_query = text("SELECT id, created_at, session_id, role FROM chat_logs ORDER BY created_at DESC LIMIT 10")
        chat_logs_result = connection.execute(chat_logs_query)
        chat_logs = chat_logs_result.fetchall()

        if chat_logs:
            print(f"Found {len(chat_logs)} chat log(s):")
            for row in chat_logs:
                print(f"  ID: {row[0]}, Created: {row[1]}, Session: {row[2]}, Role: {row[3]}")
        else:
            print("No records found in the 'chat_logs' table.")

except Exception as e:
    print(f"\n--- An error occurred ---")
    print(e)
