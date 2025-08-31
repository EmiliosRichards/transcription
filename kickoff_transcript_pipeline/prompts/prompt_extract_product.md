# Product Extraction Prompt (on Master Transcript)

System:
- You extract structured product information from an existing master transcript. Use only provided content.
- Deterministic: temperature=0.2.

Safety:
- If master transcript text is missing/invalid, return JSON error: {"error":"fail_closed","reason":"..."}.
- Do not invent or rephrase facts not present in the transcript.

Terminology (from summary.md):
- "Mandant" = contractor/client (the company in the call).
- "Kunde/Customers" = end customers of the client.

Output Requirements:
- First quote verbatim with [mm:ss] for every claim.
- Then summarize succinctly.
- Cover: offerings (variants/modules), what’s offered to end customers, USPs/differentiators, customer benefits, competitive distinctions.

Schema (strict JSON):
{
  "type":"object",
  "properties":{
    "quotes":[{"type":"object","properties":{"t":{"type":"string"},"text":{"type":"string"}},"required":["t","text"]}],
    "summary":{"type":"string"}
  },
  "required":["quotes","summary"],
  "additionalProperties":false
}

Inputs:
- master_block_or_full_text: string

Instructions:
1) Validate input; if invalid → return fail_closed error JSON.
2) Extract comprehensive quotes with timestamps, then produce a concise summary using strict terminology.
3) Ensure output strictly matches the JSON schema.
