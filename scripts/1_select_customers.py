import pandas as pd
import numpy as np

def main():
    # Load the datasets
    try:
        df_summary = pd.read_csv('data/sql imports/_SELECT_c_phone_AS_phone_cm_campaign_AS_campaign_name_COUNT_r_id_202507241545.csv', on_bad_lines='skip')
        df_recordings = pd.read_csv('data/sql imports/_SELECT_r_id_AS_recording_id_r_location_c_phone_AS_phone_cm_camp_202507241546.csv', on_bad_lines='skip')
    except FileNotFoundError as e:
        print(f"Error loading CSV files: {e}")
        exit()

    # --- Data Cleaning and Merging ---
    df_summary_cleaned = df_summary[['phone', 'total_recordings']].copy()
    df_recordings_cleaned = df_recordings[['recording_id', 'location', 'phone', 'duration_seconds']].copy()
    df_recordings_cleaned.rename(columns={'location': 'recording_url'}, inplace=True)

    # --- Proportional Customer Sampling ---
    def get_frequency_category(count):
        if count == 1:
            return 'Low (1)'
        elif 2 <= count <= 5:
            return 'Medium (2-5)'
        else: # > 5
            return 'High (6+)'

    df_summary_cleaned['frequency_category'] = df_summary_cleaned['total_recordings'].apply(get_frequency_category)

    population_distribution = df_summary_cleaned['frequency_category'].value_counts(normalize=True)
    print("Population Distribution of Customers:")
    print(population_distribution)

    total_sample_size = 100
    sample_sizes = (population_distribution * total_sample_size).round().astype(int)

    while sample_sizes.sum() != total_sample_size:
        if sample_sizes.sum() > total_sample_size:
            sample_sizes[sample_sizes.idxmax()] -= 1
        else:
            sample_sizes[sample_sizes.idxmin()] += 1

    print("\nProportional Sample Sizes for 100 Customers:")
    print(sample_sizes)

    selected_customers = pd.DataFrame()
    for category, size in sample_sizes.items():
        stratum = df_summary_cleaned[df_summary_cleaned['frequency_category'] == category]
        if len(stratum) < size:
            sample = stratum
        else:
            sample = stratum.sample(n=size, random_state=42)
        selected_customers = pd.concat([selected_customers, sample])

    # --- Gather All Recordings for Selected Customers ---
    selected_recordings = pd.merge(df_recordings_cleaned, selected_customers[['phone']], on='phone')

    # --- Save the Final List ---
    output_dir = "output/customer_journey_poc"
    os.makedirs(output_dir, exist_ok=True)
    
    # Save the list of URLs to a single file
    np.savetxt(os.path.join(output_dir, 'all_selected_urls.txt'), selected_recordings['recording_url'].tolist(), fmt='%s')

    # Save the full details to a CSV for reference
    selected_recordings.to_csv(os.path.join(output_dir, 'all_selected_recordings_details.csv'), index=False)

    print(f"\nSuccessfully selected {len(selected_customers)} customers and gathered {len(selected_recordings)} total recordings.")
    print(f"Details and URLs saved in '{output_dir}'.")

if __name__ == "__main__":
    import os
    main()