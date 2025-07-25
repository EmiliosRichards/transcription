# System Architecture for Advanced Analysis Pipeline

This document outlines the technical specifications for each script in the advanced analysis pipeline.

---

## Phase 5: Advanced Batch Analysis

### 5.1: `7_aggregate_transcripts.py` (Modification)

*   **Purpose**: To aggregate individual call transcripts for each customer into a single "journey" document, now with integrated tagging.
*   **Input**: `output/customer_journey_poc/transcripts/` (directory of individual call transcripts).
*   **Output**: `output/customer_journey_poc/tagged_aggregated_journeys.csv`
*   **Core Logic**:
    1.  Load the existing `5_tag_transcripts.py` script's functionality as a module.
    2.  For each customer (phone number), iterate through their individual call transcripts.
    3.  For each transcript, run the tagging function to get structured tags.
    4.  Append the tags directly into the transcript text (e.g., `Speaker A: Hello. <tag>gatekeeper_engaged</tag>`).
    5.  Concatenate all tagged transcripts for a customer into a single string.
    6.  Save the results to a new CSV file with columns `phone_number` and `tagged_journey_transcript`.

### 5.2: `9_create_analysis_batches.py`

*   **Purpose**: To read the aggregated journeys and group them into token-based batches for efficient processing.
*   **Input**: `output/customer_journey_poc/tagged_aggregated_journeys.csv`.
*   **Output**: A new directory `output/customer_journey_poc/batches/` containing multiple CSV files (e.g., `batch_1.csv`, `batch_2.csv`).
*   **Core Logic**:
    1.  Load the input CSV into a pandas DataFrame.
    2.  Use a token counting library (like `tiktoken`) to calculate the token count for each `tagged_journey_transcript`.
    3.  Define a `MAX_TOKENS_PER_BATCH` constant (e.g., 100,000).
    4.  Iterate through the DataFrame, adding journeys to a batch until the cumulative token count approaches the limit.
    5.  When a batch is full, save it as a numbered CSV file in the output directory and start a new batch.
    6.  Ensure the final batch is also saved.

### 5.4: `10_run_batch_analysis.py`

*   **Purpose**: To run the Level 1 qualitative analysis on each batch.
*   **Input**: `output/customer_journey_poc/batches/` directory.
*   **Output**: A new directory `output/customer_journey_poc/batch_summaries/` containing multiple text files (e.g., `summary_1.txt`, `summary_2.txt`).
*   **Core Logic**:
    1.  Read the `prompts/analyze_batch_qualitative.txt` prompt.
    2.  Iterate through each `batch_n.csv` file in the input directory.
    3.  For each batch, concatenate all `tagged_journey_transcript` rows, separated by `"--- JOURNEY SEPARATOR ---"`.
    4.  Inject this concatenated text into the prompt.
    5.  Send the completed prompt to the GPT-4 API.
    6.  Save the returned summary as a corresponding `summary_n.txt` file.

### 5.5: `11_run_final_aggregation.py`

*   **Purpose**: To aggregate the individual batch summaries into a final qualitative report.
*   **Input**: `output/customer_journey_poc/batch_summaries/` directory.
*   **Output**: `output/customer_journey_poc/Final_Qualitative_Report.md`.
*   **Core Logic**:
    1.  Read the `prompts/aggregate_summaries_qualitative.txt` prompt.
    2.  Iterate through each `summary_n.txt` file, reading its content.
    3.  Concatenate all summary contents into a single string.
    4.  Inject this string into the final aggregation prompt.
    5.  Send the completed prompt to the GPT-4 API.
    6.  Save the result as the final markdown report.

---

## Phase 6: Statistical Analysis Track

### 6.2: `12_run_statistical_analysis.py`

*   **Purpose**: To extract structured statistical data from each individual journey.
*   **Input**: `output/customer_journey_poc/tagged_aggregated_journeys.csv`.
*   **Output**: `output/customer_journey_poc/journey_stats.csv`.
*   **Core Logic**:
    1.  Read the `prompts/extract_stats_quantitative.txt` prompt.
    2.  Iterate through each row (each journey) in the input CSV.
    3.  For each journey, send its `tagged_journey_transcript` to the GPT-4 API with the stats extraction prompt.
    4.  The API should return a JSON object. Parse this JSON.
    5.  Append the parsed data as a new row to a list of dictionaries.
    6.  After processing all journeys, convert the list of dictionaries into a pandas DataFrame and save it as `journey_stats.csv`.

### 6.3: `13_aggregate_stats.py`

*   **Purpose**: To analyze the extracted stats and generate a final quantitative report.
*   **Input**: `output/customer_journey_poc/journey_stats.csv`.
*   **Output**: `output/customer_journey_poc/Final_Statistical_Report.csv`.
*   **Core Logic**:
    1.  Load the input CSV into a pandas DataFrame.
    2.  Perform various pandas operations to calculate aggregate statistics:
        *   Count of `successful` vs. `unsuccessful` outcomes.
        *   Percentage of journeys containing each tag.
        *   Average `total_call_count` for successful vs. unsuccessful journeys.
        *   Correlation between certain tags and success.
    3.  Format these findings into a new, summary DataFrame.
    4.  Save the summary DataFrame to the final statistical report CSV.