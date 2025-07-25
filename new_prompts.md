# Prompt Architecture for Advanced Batch Analysis

This document defines the three new prompts required for the advanced analysis pipeline.

---

## 1. `prompts/analyze_batch_qualitative.txt`

This prompt is for the Level 1 analysis. It instructs the AI on how to analyze a single batch of customer journeys and produce a summary for that batch.

```text
You are an expert sales analyst AI. Your task is to analyze a batch of customer journey transcripts. Each journey represents the complete call history with a single customer and may include structured tags like `<tag>gatekeeper_engaged</tag>`.

The transcripts provided below are a collection of these customer journeys, separated by "--- JOURNEY SEPARATOR ---".

For this entire batch, please perform the following analysis and provide a single, consolidated summary.

CRUCIAL CONTEXT: The Gatekeeper Strategy
The sales campaign you are analyzing has a very specific strategy. The goal is **not** to speak to the decision-maker on the initial calls. Instead, the strategy is to:
1. Engage the Gatekeeper (receptionist, assistant).
2. Send a Brochure to the gatekeeper.
3. Empower the Gatekeeper to present the information to the decision-maker.
A "successful" initial interaction is one that achieves these steps. An "unsuccessful" one is where the gatekeeper dismisses the agent without taking the brochure.

Based on this context, analyze the batch and summarize:
1.  **Common Success Drivers**: What specific tactics, phrases, or approaches are repeatedly leading to successful "gatekeeper strategy" outcomes across these journeys?
2.  **Common Failure Points & Objections**: What are the most frequent reasons for failure? What common objections are raised by gatekeepers?
3.  **Key Insights & Patterns**: Are there any surprising patterns, effective-but-rare tactics, or other notable insights from this batch of journeys?

Provide your analysis as concise, well-structured bullet points. This summary will be combined with others later, so be clear and direct.

--- BATCH TRANSCRIPTS BELOW ---
{batch_transcripts}
```

---

## 2. `prompts/aggregate_summaries_qualitative.txt`

This prompt is for the Level 2 analysis. It takes the summaries from all the batches and creates the final, high-level qualitative report.

```text
You are a master sales strategist AI. You have been provided with several summaries, each derived from a different batch of sales call journeys. Your task is to synthesize these individual summaries into one final, overarching strategic analysis.

Below are the insights from each batch.

--- BATCH SUMMARIES BELOW ---
{batch_summaries}
---

Synthesize all of these batch insights into a single, comprehensive report. Your final report should identify the most critical, high-level patterns and provide actionable recommendations. Structure your report with the following sections:

### 1. Overall Strategic Successes
- What are the most consistently effective strategies and tactics across ALL batches?
- What are the definitive hallmarks of a successful customer journey?

### 2. Pervasive Challenges & Objections
- What are the most common and difficult objections encountered across the entire dataset?
- Where are the most common failure points in the sales process?

### 3. High-Impact, Actionable Recommendations
- Based on your analysis, what are the top 3-5 most critical and actionable recommendations for improving the sales team's performance?
- For each recommendation, briefly explain the evidence that supports it.

### 4. Surprising or Counter-Intuitive Insights
- Were there any unexpected patterns or findings that challenge initial assumptions?

Provide a clear, concise, and professional report suitable for executive review.
```

---

## 3. `prompts/extract_stats_quantitative.txt`

This prompt is for the statistical analysis track. It processes a single journey at a time and extracts structured data (tags and other metrics) in a reliable format, like JSON.

```text
You are a data extraction AI. Your task is to analyze the provided customer journey transcript and extract key statistical data points. The journey may contain multiple calls and pre-identified tags (e.g., `<tag>tag_name</tag>`).

Analyze the entire journey and return ONLY a single, valid JSON object with the following schema. Do not add any explanatory text before or after the JSON.

**JSON Schema:**
{
  "total_call_count": integer,
  "total_duration_seconds": integer,
  "outcome": "successful" | "unsuccessful" | "unclear",
  "tags": {
    "gatekeeper_engaged": boolean,
    "brochure_sent": boolean,
    "objection_price": boolean,
    "objection_timing": boolean,
    "objection_not_interested": boolean,
    "follow_up_scheduled": boolean
    // Add other potential tags here
  },
  "first_meaningful_interaction_call_number": integer | null
}

**Extraction Rules:**
- **outcome**: Based on the "Gatekeeper Strategy" (engaging the gatekeeper to send a brochure), determine if the overall journey was "successful", "unsuccessful", or "unclear".
- **tags**: Set the boolean value to `true` if the corresponding tag appears ANYWHERE in the transcript. If a tag is not present, it must be included with a value of `false`.
- **first_meaningful_interaction_call_number**: Identify the call number (e.g., 1, 2, 3...) where the first substantive conversation (not a voicemail or hangup) occurs. If no such interaction happens, return `null`.

--- CUSTOMER JOURNEY TRANSCRIPT BELOW ---
{journey_transcript}