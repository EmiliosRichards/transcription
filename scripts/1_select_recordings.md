# Recording Selection Script Specification (V2)

This document outlines the Python script for selecting 100 recordings for the POC analysis. This version uses a **proportional stratified sampling** method to ensure the sample is representative of the entire dataset's distribution.

## 1. Objective

The script will parse the two provided CSV files, merge them, and then apply a proportional stratified sampling method to select 100 recordings. The selection will be based on the actual distribution of call frequency per phone number to ensure a representative and varied sample.

## 2. Python Script

```python
import pandas as pd
import numpy as np

# --- 1. Load the Datasets ---
try:
    # This file contains the total number of recordings per phone number
    df_summary = pd.read_csv('data/sql imports/_SELECT_c_phone_AS_phone_cm_campaign_AS_campaign_name_COUNT_r_id_202507241545.csv', on_bad_lines='skip')
    # This file contains individual recording details, including duration and URL
    df_recordings = pd.read_csv('data/sql imports/_SELECT_r_id_AS_recording_id_r_location_c_phone_AS_phone_cm_camp_202507241546.csv', on_bad_lines='skip')
except FileNotFoundError as e:
    print(f"Error loading CSV files: {e}")
    exit()

# --- 2. Data Cleaning and Merging ---

# Clean up the summary and recordings dataframes
df_summary_cleaned = df_summary[['phone', 'total_recordings']].copy()
df_recordings_cleaned = df_recordings[['recording_id', 'location', 'phone', 'duration_seconds']].copy()
df_recordings_cleaned.rename(columns={'location': 'recording_url'}, inplace=True)

# Merge the two dataframes to get total_recordings for each individual recording
df_merged = pd.merge(df_recordings_cleaned, df_summary_cleaned, on='phone')

# --- 3. Proportional Stratified Sampling ---

# Define the strata based on 'total_recordings'
def get_frequency_category(count):
    if count == 1:
        return 'Low (1)'
    elif 2 <= count <= 5:
        return 'Medium (2-5)'
    else: # > 5
        return 'High (6+)'

df_merged['frequency_category'] = df_merged['total_recordings'].apply(get_frequency_category)

# Calculate the distribution of frequency categories in the entire dataset
population_distribution = df_merged['frequency_category'].value_counts(normalize=True)
print("Population Distribution:")
print(population_distribution)

# Determine the sample size for each stratum based on the population distribution
total_sample_size = 100
sample_sizes = (population_distribution * total_sample_size).round().astype(int)

# Adjust sample sizes to ensure they sum to exactly 100 due to rounding
while sample_sizes.sum() != total_sample_size:
    if sample_sizes.sum() > total_sample_size:
        sample_sizes[sample_sizes.idxmax()] -= 1
    else:
        sample_sizes[sample_sizes.idxmin()] += 1

print("\nProportional Sample Sizes for 100 recordings:")
print(sample_sizes)

# Perform stratified sampling based on the calculated proportional sizes
selected_recordings = pd.DataFrame()

for category, size in sample_sizes.items():
    stratum = df_merged[df_merged['frequency_category'] == category]
    
    # If the stratum has fewer recordings than the desired sample size, take all of them
    if len(stratum) < size:
        sample = stratum
    else:
        sample = stratum.sample(n=size, random_state=42) # for reproducibility
        
    selected_recordings = pd.concat([selected_recordings, sample])

# --- 4. Save the Final List ---
final_selection = selected_recordings[['recording_id', 'recording_url', 'duration_seconds', 'phone', 'total_recordings', 'frequency_category']]

# Save the list of URLs to a text file
np.savetxt('output/selected_recordings_urls.txt', final_selection['recording_url'].values, fmt='%s')

# Save the full details to a CSV for reference
final_selection.to_csv('output/selected_recordings_details.csv', index=False)

print(f"\nSuccessfully selected {len(final_selection)} recordings based on proportional distribution.")
print(f"Final selection counts:\n{final_selection['frequency_category'].value_counts()}")
print("Details saved to 'output/selected_recordings_details.csv'")
print("URLs saved to 'output/selected_recordings_urls.txt'")

```

## 3. Next Steps

Please review this updated, more robust plan. Once you approve, we can proceed to the "Code" mode to execute this script and generate the representative sample.