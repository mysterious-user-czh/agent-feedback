$ErrorActionPreference = 'Stop'
$checks = [ordered]@{
  exit_zero = ($env:EVAL_EXIT_CODE -eq '0')
  input_unchanged = ((Get-Content -Raw -Encoding UTF8 'fixtures/input.txt') -ceq 'P4_CAPTURE_OK')
  output_exact = ((Get-Content -Raw -Encoding UTF8 'artifacts/output.txt') -ceq 'P4_CAPTURE_OK')
}
$checks | ConvertTo-Json -Compress
if ($checks.Values -contains $false) { exit 1 }
exit 0
