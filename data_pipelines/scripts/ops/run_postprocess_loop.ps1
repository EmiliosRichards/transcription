param(
  [Parameter(Mandatory=$true)] [string]$B2Prefix,
  [Parameter(Mandatory=$true)] [string]$Bucket,
  [string]$OutputDir = 'data_pipelines\data\postprocessed',
  [string]$DbUrl = $env:DATABASE_URL,
  [int]$MaxWorkers = 4,
  [int]$BatchSize = 1000,
  [int]$ClaimTtlMinutes = 60,
  [int]$CooldownMinutes = 60,
  [int]$CbDbFailThreshold = 3,
  [int]$CbB2FailThreshold = 3,
  [ValidateSet('skip','exit')] [string]$CbOpenAction = 'skip',
  [switch]$NoLocalSave,
  [switch]$DryProbeOnly
)

function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 2 }
function Info($msg) { Write-Host $msg -ForegroundColor Cyan }

if (-not $DbUrl) { Fail "DATABASE_URL is not set in this shell." }
if (-not $env:BACKBLAZE_B2_S3_ENDPOINT) { Fail "BACKBLAZE_B2_S3_ENDPOINT not set." }
if (-not $env:BACKBLAZE_B2_BUCKET) { Fail "BACKBLAZE_B2_BUCKET not set." }
if (-not $env:BACKBLAZE_B2_KEY_ID) { Fail "BACKBLAZE_B2_KEY_ID not set." }
if (-not $env:BACKBLAZE_B2_APPLICATION_KEY) { Fail "BACKBLAZE_B2_APPLICATION_KEY not set." }

Info "Preflight: DB connectivity"
@'
import os
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL'].replace('postgresql+asyncpg','postgresql+psycopg2')
e = create_engine(url)
with e.connect() as c:
  c.execute(text('select 1'))
print('DB OK')
'@ | python - | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "DB preflight failed." }

Info "Preflight: B2 ping"
python chatbot_app/backend/app/quick_b2_ping.py | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "B2 ping failed." }

$argsCommon = @(
  '--b2-prefix', $B2Prefix,
  '--bucket', $Bucket,
  '--output-dir', $OutputDir,
  '--db-url', $DbUrl,
  '--require-db', '--db-failure-threshold', '3',
  '--select-from-db', '--use-claims', '--claim-ttl-minutes', "$ClaimTtlMinutes",
  '--max-workers', "$MaxWorkers",
  '--cooldown-minutes', "$CooldownMinutes",
  '--upload-to-b2', '--b2-out-json-prefix', 'dexter/postprocessed/json', '--b2-out-txt-prefix', 'dexter/postprocessed/txt',
  '--llm-enabled', '--llm-required', '--llm-model', 'gpt-5-mini',
  '--prompt-file', 'chatbot_app/backend/app/prompts/post_process_with_timestamps.txt'
)
if ($NoLocalSave.IsPresent) { $argsCommon += @('--no-local-save') }

# Circuit breaker
$argsCommon += @('--cb-db-fail-threshold', "$CbDbFailThreshold", '--cb-b2-fail-threshold', "$CbB2FailThreshold", '--cb-open-action', $CbOpenAction)

$probeArgs = $argsCommon | Where-Object { $_ -ne '--use-claims' }

Info "Probe: selecting remaining items (dry-run)"
python data_pipelines/scripts/post_process_v2.py @probeArgs --max-files 5 --dry-run | Write-Host
if ($DryProbeOnly) { exit 0 }

Info "Starting batch loop (BatchSize=$BatchSize, MaxWorkers=$MaxWorkers)"
while ($true) {
  python data_pipelines/scripts/post_process_v2.py @argsCommon --max-files $BatchSize
  if ($LASTEXITCODE -ne 0) { Fail "Batch run exited with error." }
  $probe = (python data_pipelines/scripts/post_process_v2.py @probeArgs --max-files 1 --dry-run) | Select-String 'Selected: '
  if (-not $probe) { break }
  Start-Sleep -Seconds 5
}

Info "Loop complete. Consider reconciliation checks in docs/dexter_reconciliation_plan.md"


