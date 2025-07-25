import os
import requests
from tqdm import tqdm

# --- 1. Setup ---
URL_FILE = 'output/customer_journey_poc/all_selected_urls.txt'
OUTPUT_DIR = 'data/audio/selected_for_poc'

# Create the output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 2. Read URLs ---
try:
    with open(URL_FILE, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    print(f"Error: The file {URL_FILE} was not found.")
    print("Please run the selection script (1_select_recordings.py) first.")
    exit()

# --- 3. Download Files ---
print(f"Found {len(urls)} URLs to download.")

for url in tqdm(urls, desc="Downloading audio files"):
    try:
        # Extract filename from URL
        filename = url.split('/')[-1]
        output_path = os.path.join(OUTPUT_DIR, filename)

        # Check if the file already exists to avoid re-downloading
        if os.path.exists(output_path):
            # print(f"Skipping {filename}, already exists.")
            continue

        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for bad status codes

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    except requests.exceptions.RequestException as e:
        print(f"\nError downloading {url}: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred for {url}: {e}")

print(f"\nDownloads complete. Files are saved in '{OUTPUT_DIR}'.")