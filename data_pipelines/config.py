from pathlib import Path

# --- Base Directories ---
# The root directory of the data_pipelines module.
# All other paths are relative to this.
PIPELINE_ROOT = Path(__file__).parent.resolve()

# --- Input Data ---
DATA_DIR = PIPELINE_ROOT / "data"
SQL_IMPORTS_DIR = DATA_DIR / "sql imports"
SPEAKER_PROFILES_DIR = DATA_DIR / "speaker_profiles"
AUDIO_DIR = DATA_DIR / "audio"
UNPROCESSED_AUDIO_DIR = AUDIO_DIR / "unprocessed"

# --- Output Data ---
OUTPUT_DIR = PIPELINE_ROOT / "output"
CUSTOMER_JOURNEY_POC_DIR = OUTPUT_DIR / "customer_journey_poc"
TRANSCRIPTIONS_DIR = OUTPUT_DIR / "transcriptions"
MISTRAL_TRANSCRIPTIONS_DIR = OUTPUT_DIR / "mistral_transcriptions"
PROCESSED_DIR = OUTPUT_DIR / "processed"
OPENAI_TRANSCRIPTIONS_DIR = OUTPUT_DIR / "openai_transcriptions"
BATCHES_DIR = CUSTOMER_JOURNEY_POC_DIR / "batches"
BATCH_SUMMARIES_DIR = CUSTOMER_JOURNEY_POC_DIR / "batch_summaries"

# --- Logs ---
LOGS_DIR = OUTPUT_DIR / "logs"
CONTEXT_LOGS_DIR = LOGS_DIR / "context"
RESPONSES_LOGS_DIR = LOGS_DIR / "responses"

# --- Prompts ---
PROMPTS_DIR = PIPELINE_ROOT / "prompts"

# --- Temporary Files ---
TEMP_DIR = PIPELINE_ROOT / "temp"

def ensure_dirs_exist():
    """
    Creates all the necessary output and logging directories if they don't already exist.
    This can be called at the start of any pipeline script.
    """
    dirs_to_create = [
        DATA_DIR, SQL_IMPORTS_DIR, SPEAKER_PROFILES_DIR, AUDIO_DIR,
        UNPROCESSED_AUDIO_DIR, OUTPUT_DIR, CUSTOMER_JOURNEY_POC_DIR,
        TRANSCRIPTIONS_DIR, MISTRAL_TRANSCRIPTIONS_DIR, PROCESSED_DIR,
        BATCHES_DIR, BATCH_SUMMARIES_DIR, LOGS_DIR, CONTEXT_LOGS_DIR,
        RESPONSES_LOGS_DIR, PROMPTS_DIR, TEMP_DIR, OPENAI_TRANSCRIPTIONS_DIR
    ]
    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)
