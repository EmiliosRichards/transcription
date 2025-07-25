import pandas as pd
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Aggregate extracted stats into a final report.")
    parser.add_argument(
        "--input_file",
        default='output/customer_journey_poc/journey_stats.csv',
        help="Path to the CSV file with extracted journey stats."
    )
    parser.add_argument(
        "--output_file",
        default='output/customer_journey_poc/Final_Statistical_Report.csv',
        help="Path to save the final statistical report."
    )
    args = parser.parse_args()

    # --- 1. Load Data ---
    try:
        df = pd.read_csv(args.input_file)
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input_file}")
        print("Please run the stats extraction script (12_run_statistical_analysis.py) first.")
        return

    # --- 2. Perform Analysis ---
    print("Performing statistical analysis...")
    
    # Create a list to hold our summary data
    summary_data = []

    # Overall counts
    total_journeys = len(df)
    summary_data.append({"Metric": "Total Customer Journeys", "Value": total_journeys})

    # Outcome analysis
    outcome_counts = df['outcome'].value_counts()
    for outcome, count in outcome_counts.items():
        summary_data.append({"Metric": f"Outcome: {outcome}", "Value": count})
        summary_data.append({"Metric": f"Outcome: {outcome} (%)", "Value": f"{(count / total_journeys) * 100:.2f}%"})

    # Tag analysis
    tag_columns = [col for col in df.columns if col.startswith('tags.')]
    # Clean column names for display
    clean_tag_names = [col.replace('tags.', '') for col in tag_columns]
    
    # Convert boolean tags to numeric for sum
    for col in tag_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    tag_counts = df[tag_columns].sum()
    for i, (tag_name, count) in enumerate(tag_counts.items()):
        clean_name = clean_tag_names[i]
        summary_data.append({"Metric": f"Tag Count: {clean_name}", "Value": count})
        summary_data.append({"Metric": f"Tag Prevalence: {clean_name} (%)", "Value": f"{(count / total_journeys) * 100:.2f}%"})

    # Call metrics analysis
    avg_call_count = df['total_call_count'].mean()
    summary_data.append({"Metric": "Average Calls per Journey", "Value": f"{avg_call_count:.2f}"})

    avg_call_count_success = df[df['outcome'] == 'successful']['total_call_count'].mean()
    summary_data.append({"Metric": "Average Calls for 'Successful' Journey", "Value": f"{avg_call_count_success:.2f}"})

    avg_call_count_fail = df[df['outcome'] == 'unsuccessful']['total_call_count'].mean()
    summary_data.append({"Metric": "Average Calls for 'Unsuccessful' Journey", "Value": f"{avg_call_count_fail:.2f}"})

    # --- 3. Save Report ---
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv(args.output_file, index=False)

    print(f"\nSuccessfully generated statistical report and saved to '{args.output_file}'.")
    print("\n--- Report Summary ---")
    print(summary_df)
    print("--------------------")


if __name__ == "__main__":
    main()