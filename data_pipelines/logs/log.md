Dexter All campaigns 28-08-2025

python data_pipelines\scripts\transcribe_gpt4o.py `
  --b2-prefix "dexter/audio" `
  --output-dir "data_pipelines\data\transcriptions\whisper1" `
  --model "whisper-1" `
  --timestamps segment `
  --language de `
  --prompt-file "data_pipelines/whisper_dexter_prompt" `
  --preprocess --pp-sr 16000 --pp-mono 1 `
  --tail-guard `
  --bucket "$env:BACKBLAZE_B2_BUCKET" `
  --db-url "$env:DATABASE_URL" `
  --db-audio-table "media_pipeline.audio_files" `
  --db-transcriptions-table "media_pipeline.transcriptions" `
  --db-skip-existing `
  --upload-transcripts-to-b2 `
  --b2-out-prefix "dexter/transcriptions/json" `
  --upload-transcripts-txt-to-b2 `
  --b2-out-txt-prefix "dexter/transcriptions/txt" `
  --limit 10