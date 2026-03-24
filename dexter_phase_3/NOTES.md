# Dexter Phase 3 — Notes for Team

## 1. AP Name Tracking in Dialfire

The `AP_Vorname` and `AP_Nachname` fields in Dialfire contacts are almost always empty for Dexter contacts. This means we have no reliable source for the decision maker's name — we're relying entirely on the LLM extracting names from garbled ASR transcripts, which is unreliable.

**Action:** Push agents to fill in AP name fields after calls. Even a last name ("Herr Weddeck") is valuable. This directly improves pitch quality — templates like "Da sagten Sie mir, dass [mein AP] aktuell nicht erreichbar sei" sound much better with a real name than "der zuständigen Person".

## 2. Programmatic System Pre-Scan

For contacts with many calls (50+), the system name (Vivendi, Senso, Medifox, etc.) might only be mentioned in an early call that gets truncated from the LLM context window (3000 word limit).

**Idea:** Before sending to the LLM, grep all transcripts for known system names (the list already exists in the Whisper prompt: Medifox Dan, Connext Vivendi, Senso, CGM, CareCloud, Sinfonie, myneva, etc.) and inject any matches as a hint in the LLM prompt. This is cheap (no API call, just string matching) and ensures we never lose system info to truncation.

## 4. Improved Whisper Prompt for Future Transcriptions

The current Whisper prompt is a flat keyword list. A contextual prompt would improve accuracy — especially for proper nouns, role titles, and software names that ASR tends to garble.

**Current prompt (whisper-1):**
```
Dexter, Voize, SIS (Strukturierte Informationssammlung), Medifox Dan (Medifox, MD, Dan), Connext Vivendi (Vivendi, Connext), Senso, CGM (CompuGroup Medical), C&S (Computer und Software GmbH), CareCloud, Sinfonie, myneva, OptaData, Noventi, Cairful, Euregon, Micos, Curasoft
```

**Recommended prompt:**
```
Das folgende Gespräch ist ein Outbound-Kaltanruf der Firma Dexter an ein Pflegeheim oder einen ambulanten Pflegedienst. Dexter bietet eine KI-App für Sprachdokumentation in der Pflege an. Der Agent stellt sich vor und versucht, mit der Heimleitung, PDL oder Einrichtungsleitung zu sprechen.

Häufig genannte Software-Systeme: Medifox Dan, Connext Vivendi, Senso, Sinfonie, myneva, CareCloud, CGM, Euregon, Micos, Curasoft, Noventi, OptaData, SNAP, DM7, Voize, SIS.

Häufig genannte Rollen: PDL, Pflegedienstleitung, Heimleitung, Einrichtungsleitung, Verwaltungsleitung, Geschäftsführung, Träger, Stiftung, Bürgerspital.
```

**Why better:**
- Context tells the model what kind of conversation to expect (cold call → care home)
- Proper nouns with variants help recognition ("Connext Vivendi" not just "Vivendi")
- Role names (PDL, Heimleitung) are domain jargon that ASR garbles without hints

**Future consideration:** `gpt-4o-transcribe` has much better prompting support than `whisper-1` and may improve transcript quality further. Evaluate cost vs quality tradeoff.

## 3. Transcription of New Calls

Calls after Aug 25, 2025 exist in the DB as `audio_files` rows but may not be transcribed yet. The transcription pipeline (`data_pipelines/` scripts and Gateway Worker) needs to be run for new recordings. All existing Dexter calls (97,816) are transcribed with OpenAI Whisper-1 using a German-language prompt with care software keywords.
