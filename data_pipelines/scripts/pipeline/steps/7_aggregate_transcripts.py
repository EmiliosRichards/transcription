import os
import sys
# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import glob
import json
import pandas as pd
from scripts.utils.tagger import get_transcript_tag

def main():
    parser = argparse.ArgumentParser(description="Aggregate customer journey transcripts with tags.")
    parser.add_argument(
        "--input_dir",
        default='output/customer_journey_poc',
        help="Directory containing the processed customer journey subdirectories."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/tagged_aggregated_journeys.csv',
        help="Path to save the final aggregated CSV file with tags."
    )
    args = parser.parse_args()

    aggregated_data = []

    for customer_dir in glob.glob(os.path.join(args.input_dir, '*/')):
        phone_number = os.path.basename(os.path.normpath(customer_dir))
        
        json_files = sorted(glob.glob(os.path.join(customer_dir, '*.json')))
        
        full_journey_transcript = ""
        for file_path in json_files:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                transcript = data.get("full_transcript", "")
                if transcript:
                    tag = get_transcript_tag(transcript)
                    full_journey_transcript += f"<tag>{tag}</tag>\n{transcript}\n\n--- END OF CALL ---\n\n"
        
        if full_journey_transcript:
            aggregated_data.append({
                "phone_number": phone_number,
                "tagged_journey_transcript": full_journey_transcript.strip()
            })

    df = pd.DataFrame(aggregated_data)
    df.to_csv(args.output_file, index=False)
    print(f"Successfully aggregated {len(df)} customer journeys to '{args.output_file}'.")

if __name__ == "__main__":
    import argparse
    main()