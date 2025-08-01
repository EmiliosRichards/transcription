import os
from data_pipelines import config
import argparse
import json
import time
from google.generativeai.client import configure
from google.generativeai.generative_models import GenerativeModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
# To use this script, you must set your Google API key as an environment variable.
# For example, in your terminal:
# export GOOGLE_API_KEY="YOUR_API_KEY"
# Or on Windows:
# set GOOGLE_API_KEY="YOUR_API_KEY"
# Pylance may report that 'configure' and 'GenerativeModel' are not exported.
# This can be a linter issue with the google-generativeai library.
# The code is functionally correct.
configure(api_key=os.environ.get("GOOGLE_API_KEY"))

# --- LLM Prompt Template ---
PROMPT_TEMPLATE = """
You are a hyper-accurate AI assistant specializing in post-processing German ASR transcripts from business calls. Your primary goal is to clean, structure, and analyze the text with the highest accuracy.

**Primary Directive:** Generate a hyper-accurate, well-structured German transcript with clear speaker separation and precise entity extraction.

###  Contextual Business Insight:

Manuav/Berivo primarily helps its customers acquire new customers through outbound call campaigns. Consequently, typical interactions follow patterns:

- **Agents:** Clearly introduce themselves, state purpose, or confirm intent (often verifying recipient needs or interests).
- **Recipients:** Often provide brief or detailed feedback regarding interest, scheduling, objections, or next steps.

When dialogue explicitly references "acquiring new customers," "collaboration," or "topics we wanted to discuss," use logical inference:
- Typically, the **recipient (the one being called)** confirms, objects to, or clarifies the intent, especially if they mention previous conversations.
- Typically, the **caller (agent)** either clarifies, reasserts, or provides additional context when recipients question or seek clarification about the purpose.

Use these insights to make accurate inferences and adjustments when assigning speaker labels, especially if transcription errors or conversational corrections occur.

###  Conversational Dynamics and Common Scenarios:

These transcripts are from outbound business calls conducted by our call center. Typically, our agents (caller) represent either our own company (ManuAv) or one of our customers, contacting recipients to offer or discuss services aimed at acquiring new customers or establishing collaboration.

The following conversational dynamics are common and should guide your inference about speaker identity:

- **Clarifications and Corrections:**
  Occasionally, speakers might misspeak or briefly correct themselves mid-conversation (e.g., "This is about news... sorry, I mean this is about acquiring new customers"). Identify these corrections and clearly attribute lines accordingly.

- **Anticipations and Confirmations:**
  Agents often preemptively confirm or restate the recipient's intent or previous conversation context (e.g., "We spoke yesterday. This is about acquiring new customers, isn't it?"). Such lines typically come from the recipient, verifying the reason for the call, prompting the caller to clarify or expand.

- **Reasons for Objection or Decline:**
  Recipients might respond to service offerings either positively, neutrally, or negatively, often providing specific reasons for declining a conversation or request (e.g., “We currently don’t need any new groups”). Recognize these statements as coming from the recipient rather than the agent.

When assigning speaker labels, carefully analyze linguistic cues, tone, and conversational logic to ensure each line is correctly attributed to either the caller (representing ManuAv or our customer) or the recipient.

**Instructions:**

1. **Clean Transcript Text:**
    *   Correct transcription errors, spelling, punctuation, and grammar.
    *   Produce natural-sounding, fluent German sentences.
    *   If repetitive artifacts, filler words, or clearly meaningless lines occur (particularly at the end of the transcript), remove their text content entirely, provided their removal does not alter the meaning or clarity of the conversation.
    *   The transcript is in **German**. All corrections must be contextually and phonetically appropriate for the German language.

2.  **Diarize and Label Speakers:**
    *   The input transcript will NOT have any speaker labels.
    *   Assign labels based on conversational patterns, tone, greetings, context, and logical dialogue flow.
    *   Ensure the same speaker consistently has the same label throughout the conversation.

3.  **Extract Entities:**
    *   From the final corrected text, extract all instances of the following entities:
        *   **PER**: Names of people (e.g., "Melanie Haas", "Herr Hellfield").
        *   **ORG**: Company names (e.g., "Flowtech", "Berivo", "manuav").
        *   **LOC**: Locations.
        *   **DATE**: Dates and times mentioned.
        *   **MONEY**: Monetary values.

4.  **Output Format (STRICT JSON Structure):**
    Return only a single JSON object with EXACTLY two keys:
    *   `full_transcript`: A string containing the cleaned, labeled transcript, line-separated (`\\n`). Each line starts with its assigned speaker label, e.g. `[SPEAKER_01]: ...`.
    *   `entities`: A list of extracted entities as dictionaries (`{{"text": "...", "type": "..."}}`).

### Additional Context and Instructions (Call Center Context):

#### Input Transcript Format:
    *   Consists of individual unlabeled lines.
    *   Each new line may represent a continuation of the previous speaker or a speaker change.
    *   Occasional English loanwords (common in business contexts) may appear. Adapt these naturally into German if appropriate, ensuring the transcript remains fluent and contextually accurate.


#### Speaker Diarization Instructions:
    *   Intelligently infer speaker continuity or transitions line-by-line based on conversational context, linguistic cues, and dialogue coherence.
    *   Consistently label speakers throughout the conversation (`[SPEAKER_01]`, `[SPEAKER_02]`, `[AUTOMATED_MESSAGE]`).

#### Handling Ambiguous or Mistyped Names:
    *   If unclear, ambiguous, or mistyped names appear, intelligently correct them by selecting the most probable, relevant, or common name given conversational context.

    ### EXAMPLE INPUT (without speaker labels):
Herzlich Willkommen bei Flowtech.
Mein Name ist Braun.
Guten Tag.
Schönen guten Tag, Melanie Haas hier von Beribo.
Ich grüße Sie.
Hallo.
Der Hellfell momentan erreichbar.
Muss ich gerade mal schauen.
Kleinen Moment bitte.
Ja.
So, vielen Dank fürs Warten.
Ich habe ihn jetzt mal kurz gefragt.
Wir brauchen aktuell keine neuen Gruppen.
Aber er weiß doch gar nicht, worum es sich handelt.
Wir haben doch gestern miteinander gesprochen.
Es geht doch um Neuigkeiten.
Es geht doch um Neukundengewinnung, oder nicht?
Richtig, aber wir hatten ja einiges heben, was wir gerne auch besprechen wollten.
Also es hat ja jetzt nicht direkt mit Neukundengewinnung zu tun.
Also es handelt sich um Zusammenarbeit.
Okay, also ich habe ihn jetzt, wie gesagt, gefragt.
Er hat gerade im Termin gesessen.
Wir können doch gerne nochmal eine E-Mail an ihn schicken.
Das tut mir leid.
Kein Problem.
Ich danke Ihnen.
Gerne.
Tschüss.
Tschüss.
Tschüss.
Tschüss.

    ### EXAMPLE OUTPUT:
    ```json
    {{
      "full_transcript": "[SPEAKER_01]: Willkommen bei Flowtech. Mein Name ist Braun.\\n[SPEAKER_02]: Guten Tag. Guten Tag, hier ist Melanie Haas von Berivo. Grüße.\\n[SPEAKER_01]: Hallo.\\n[SPEAKER_02]: Ist Herr Hellfeld gerade verfügbar?\\n[SPEAKER_01]: Ich muss nur kurz nachfragen. Einen Moment bitte.\\n[SPEAKER_02]: Ja.\\n[SPEAKER_01]: Danke fürs Warten. Ich habe ihn nur kurz gefragt. Wir brauchen im Moment keine neuen Gruppen.\\n[SPEAKER_02]: Aber er weiß gar nicht, worum es geht.\\n[SPEAKER_01] Wir haben gestern gesprochen. Es geht doch um Neukundengewinnung, oder?\\n[SPEAKER_02]: Stimmt, aber wir hatten noch ein paar Themen, die wir auch gerne besprechen würden. Also, es hat nichts mit Neukundengewinnung zu tun.\\n[SPEAKER_02]: Es geht also um Zusammenarbeit.\\n[SPEAKER_01]: Okay, ich habe ihn wie gesagt gefragt. Er ist gerade in einer Besprechung. Du kannst ihm gerne noch eine E-Mail schicken. Tut mir leid.\\n[SPEAKER_02]: Kein Problem. Danke.\\n[SPEAKER_01]: Gern geschehen.\\n[SPEAKER_02]: Tschüss.\\n[SPEAKER_01]: Tschüss. ",
      "entities": [
        {{"text": "Flowtech", "type": "ORG"}},
        {{"text": "Braun", "type": "PER"}},
        {{"text": "Melanie Haas", "type": "PER"}},
        {{"text": "Berivo", "type": "ORG"}},
        {{"text": "Herr Hellfeld", "type": "PER"}},
        {{"text": "gestern", "type": "DATE"}}
      ]
    }}
    ```

---
**Transcript to Process:**
---
{transcription_text}
---
"""

def strip_speaker_labels(transcription_text):
    """
    Removes speaker labels like [SPEAKER_00]: from the transcript.
    """
    lines = transcription_text.splitlines()
    stripped_lines = []
    for line in lines:
        # Find the first occurrence of ']: ' and take the text after it
        marker_pos = line.find(']: ')
        if marker_pos != -1:
            stripped_lines.append(line[marker_pos + 3:])
        else:
            stripped_lines.append(line)
    return '\n'.join(stripped_lines)

def process_transcription_with_llm(transcription_text, base_filename):
    """
    Sends the transcription to a Gemini model for processing and logs the interaction.
    """
    print("Sending transcription to the LLM for processing...")
    model = GenerativeModel('gemini-1.5-pro-latest')
    prompt = PROMPT_TEMPLATE.format(transcription_text=transcription_text)

    # --- Logging ---
    config.CONTEXT_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    config.RESPONSES_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.CONTEXT_LOGS_DIR / f"{base_filename}.txt", "w", encoding="utf-8") as f:
        f.write(prompt)
    
    response = None
    try:
        response = model.generate_content(prompt)
        raw_response_text = response.text
        with open(config.RESPONSES_LOGS_DIR / f"{base_filename}.txt", "w", encoding="utf-8") as f:
            f.write(raw_response_text)

        # Clean up the response to extract the JSON part.
        cleaned_response = raw_response_text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"An error occurred while calling the LLM: {e}")
        raw_response_text = response.text if response else "No response"
        print(f"Raw response was: {raw_response_text}")
        return None

def post_process(input_path, output_path):
    """
    Runs the entire post-processing pipeline for a single file.
    """
    base_filename = os.path.splitext(os.path.basename(input_path))[0]
    print(f"--- Processing {base_filename} ---")
    
    print(f"Reading transcription from {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        transcription = f.read()

    stripped_transcription = strip_speaker_labels(transcription)
    processed_data = process_transcription_with_llm(stripped_transcription, base_filename)

    if processed_data:
        print(f"Saving processed data to {output_path}...")
        
        retries = 3
        # If a directory with the same name exists, remove it.
        if os.path.isdir(output_path):
            print(f"Warning: Found directory at {output_path}. Removing it.")
            try:
                os.rmdir(output_path)
            except OSError as e:
                print(f"Error: Could not remove directory {output_path}: {e}")
                return

        for i in range(retries):
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(processed_data, f, ensure_ascii=False, indent=4)
                print("Processing complete.")
                return  # Success
            except PermissionError as e:
                print(f"  -> PermissionError on attempt {i+1}/{retries}: {e}. Retrying in 1 second...")
                time.sleep(1)
        
        print(f"  -> Failed to save {output_path} after {retries} attempts.")
    else:
        print("Skipping file due to an error in LLM processing.")


# This script is now designed to be imported as a module.
# The main execution logic has been moved to batch_process_all.py