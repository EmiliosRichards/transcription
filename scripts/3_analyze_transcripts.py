import os
import glob
import json
import openai
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
import time

# Load environment variables from .env file
load_dotenv()

# --- 1. Setup ---
if "OPENAI_API_KEY" not in os.environ:
    print("OPENAI_API_KEY environment variable not found.")
    os.environ["OPENAI_API_KEY"] = input("Please enter your OpenAI API key: ")

openai.api_key = os.environ["OPENAI_API_KEY"]

def get_analysis_prompt(transcript):
    return f"""
    Analyze the following sales call transcript and provide a structured analysis in JSON format.

    Transcript:
    ---
    {transcript}
    ---

    Based on the transcript, provide the following:
    1.  "summary": A concise, one-sentence summary of the entire call.
    2.  "outcome": The primary outcome of the call. Choose from one of the following exact categories: "Appointment Set", "Follow-up Scheduled", "Objection - Price", "Objection - Not Interested", "Objection - Gatekeeper", "Voicemail", "Wrong Number", "No Answer", "Information Gathering".
    3.  "sentiment": A sentiment score from 1 (very negative) to 5 (very positive).
    4.  "tags": A list of relevant keywords or tags as strings (e.g., ["budget concerns", "follow-up required", "competitor mentioned"]).

    Your response MUST be a valid JSON object and nothing else.
    Example:
    {{
      "summary": "The agent attempted to schedule a demo but was met with a price objection.",
      "outcome": "Objection - Price",
      "sentiment": 2,
      "tags": ["budget concerns", "demo request"]
    }}
    """

def analyze_transcript(transcript):
    """
    Analyzes a single transcript using the LLM to extract structured data.
    """
    prompt = get_analysis_prompt(transcript)
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        if not content:
            print("Warning: LLM response was empty.")
            return {"error": "Empty response from LLM"}
        return json.loads(content)
    except json.JSONDecodeError:
        print("Warning: Failed to decode JSON from LLM response.")
        return {"error": "Invalid JSON response"}
    except Exception as e:
        print(f"An error occurred during analysis: {e}")
        # Implement a simple retry with backoff
        time.sleep(2) 
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            if not content:
                print("Warning: LLM response was empty on retry.")
                return {"error": "Empty response from LLM on retry"}
            return json.loads(content)
        except Exception as retry_e:
            print(f"Retry failed: {retry_e}")
            return {"error": str(retry_e)}


def main():
    parser = argparse.ArgumentParser(description="Analyze processed transcripts and add the analysis to the JSON files.")
    parser.add_argument(
        "--input_dir",
        default='output/customer_journey_poc',
        help="Directory containing the customer journey JSON transcript files."
    )
    args = parser.parse_args()

    json_files = glob.glob(os.path.join(args.input_dir, '**/*.json'), recursive=True)

    if not json_files:
        print(f"No .json files found in '{args.input_dir}'.")
        return

    print(f"Found {len(json_files)} transcripts to analyze.")

    for file_path in tqdm(json_files, desc="Analyzing transcripts"):
        with open(file_path, 'r+', encoding='utf-8') as f:
            try:
                data = json.load(f)
                
                # Check if the transcript has already been analyzed to avoid re-processing
                if "analysis" in data:
                    continue

                transcript = data.get("full_transcript")
                if transcript:
                    analysis_result = analyze_transcript(transcript)
                    data["analysis"] = analysis_result
                    
                    # Go back to the beginning of the file to overwrite it
                    f.seek(0)
                    json.dump(data, f, indent=2)
                    f.truncate()

            except json.JSONDecodeError:
                print(f"Warning: Skipping corrupted JSON file: {file_path}")
            except Exception as e:
                print(f"An error occurred processing {file_path}: {e}")

    print(f"\nSuccessfully analyzed transcripts and updated JSON files in '{args.input_dir}'.")

if __name__ == "__main__":
    main()