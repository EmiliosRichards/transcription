import os
import glob
import json
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Aggregate customer journey transcripts.")
    parser.add_argument(
        "--input_dir",
        default='output/customer_journey_poc',
        help="Directory containing the processed customer journey subdirectories."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/aggregated_journeys.csv',
        help="Path to save the final aggregated CSV file."
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
                full_journey_transcript += data.get("full_transcript", "") + "\n\n--- END OF CALL ---\n\n"
        
        if full_journey_transcript:
            aggregated_data.append({
                "phone_number": phone_number,
                "full_journey": full_journey_transcript.strip()
            })

    df = pd.DataFrame(aggregated_data)
    df.to_csv(args.output_file, index=False)
    print(f"Successfully aggregated {len(df)} customer journeys to '{args.output_file}'.")

if __name__ == "__main__":
    import argparse
    main()