import os
from dotenv import load_dotenv

# Define the path to the root of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# Load environment variables from the .env file in the project root
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

class Settings:
    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # --- OpenAI API ---
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # --- Google AI ---
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # --- LLM Models ---
    MAIN_LLM_MODEL: str = os.getenv("MAIN_LLM_MODEL", "gpt-4o")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    TRANSCRIPTION_MODEL: str = os.getenv("TRANSCRIPTION_MODEL", "whisper-1")

    # --- ChromaDB ---
    CHROMA_DB_PATH: str = os.getenv("CHROMA_DB_PATH", "output/chroma_db")
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "journeys_prod")
    
    # --- Data Paths ---
    EMBEDDINGS_CSV_PATH: str = os.getenv("EMBEDDINGS_CSV_PATH", "output/journeys_with_embeddings.csv")

    # --- Security ---
    API_KEY: str = os.getenv("API_KEY", "")


# Instantiate the settings
settings = Settings()

# --- Validations ---
if not settings.DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment.")
if not settings.OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is not set in the environment.")
if not settings.GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is not set in the environment.")
