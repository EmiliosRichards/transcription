PS C:\Users\emili> python data_pipelines/scripts/download_audio_from_csv.py `
>>   --csv-path "data_pipelines\data\sql imports\_SELECT_regexp_replace_trim_c_phone_0_9_g_AS_phone_manuav_2_camp_202508141439.csv" `
>>   --db-url "postgresql+psycopg2://postgres:Kii366@127.0.0.1:5433/manuav" `
>>   --table-name media_pipeline.audio_files `
>>   --output-root "data_pipelines\data\audio_downloads_tmp" `
>>   --limit 25 `
>>   --upload-to-b2 `
>>   --b2-prefix "manuav-dual-campaign" `
>>   --remove-local-after-upload


Cleared the b2 bucket then -

-- Truncate the table (deletes all rows, resets sequence)
TRUNCATE media_pipeline.audio_files RESTART IDENTITY CASCADE;




Full run of manuav campaigns

python data_pipelines/scripts/download_audio_from_csv.py `
  --csv-path "data_pipelines\data\sql imports\_SELECT_regexp_replace_trim_c_phone_0_9_g_AS_phone_manuav_2_camp_202508141439.csv" `
  --db-url "postgresql+psycopg2://postgres:Kii366@127.0.0.1:5433/manuav" `
  --table-name media_pipeline.audio_files `
  --output-root "data_pipelines\data\audio_downloads_tmp" `
  --upload-to-b2 `
  --b2-prefix "manuav-dual-campaign" `
  --remove-local-after-upload