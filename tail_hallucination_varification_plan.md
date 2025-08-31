- What we’re testing now
  - Tail hallucination hypothesis on PR_4656ab3d-… by:
    - Audio prep: clean re-encode (16 kHz mono), tail-silence trimming, and “last-20s” clip to stress-test the ending.
    - Model settings: force language=de; deterministic decoding (temp=0); for OSS Whisper: vad_filter=true and condition_on_previous_text=false.
    - Cross-model check: compare the final segment text for baseline vs trimmed vs last-20s to see if the fabricated “please don’t call again / thanks bye” disappears.

- Why confidence wasn’t mentioned yet
  - OpenAI gpt‑4o(-mini) transcribe doesn’t expose usable per-segment confidence/logprobs in the JSON we receive.
  - Whisper API (whisper‑1) verbose_json can expose segment-level fields (e.g., avg_logprob, no_speech_prob) and is suitable for confidence-based filtering.
  - OSS Whisper (faster‑whisper) returns segments/words; while it doesn’t provide the exact “avg_logprob/no_speech_prob” fields from OpenAI’s verbose_json, we can still threshold using segment presence, word timing density, VAD results, or add WhisperX alignment to validate the last segment.

- What else to test (next)
  - Confidence-based tail guard (for models that support it):
    - Whisper API: drop last segment if no_speech_prob is high or avg_logprob is very low.
    - OSS Whisper: add WhisperX alignment; drop the last segment if alignment fails or word timings are sparse/erratic.
  - VAD/silence thresholds:
    - Try different tail trims (e.g., silenceremove stop_threshold −30 to −40 dB; stop_duration 0.5–1.5s) and confirm the hallucination disappears without cutting real speech.
  - Channel/sample-rate quirks:
    - Ensure mono, 16 kHz; if stereo originals exist, test left vs right channel extraction (sometimes one channel is near-silent).
  - Decoding/conditioning:
    - For OSS Whisper, confirm temperature=0 and condition_on_previous_text=false reduce “story finishing”.
  - Language enforcement:
    - Verify language=de set everywhere; test a run without it to confirm drift increases (for comparison only).
  - Chunking effects:
    - Transcribe in fixed windows near the end (e.g., last 30s vs full file) to isolate context-carryover effects.

- Outcome you should expect
  - If it’s a tail hallucination, the fabricated goodbye should disappear on the trimmed audio across all models, and especially on OSS Whisper with deterministic/VAD settings.
  - Whisper API/OSS runs can be extended with a confidence/alignment-based “tail guard” later; gpt‑4o/minis benefit mainly from pre-trim since confidences aren’t exposed.