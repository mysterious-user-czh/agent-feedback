$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$checks = [ordered]@{
  exit_zero = ($env:EVAL_EXIT_CODE -eq '0')
  input_unchanged = ((Get-FileHash 'fixtures/body.docx' -Algorithm SHA256).Hash.ToLower() -eq '836a7567a0709eb16e5f5c387429b6334ef58f58ecfcf96e7708a85f527d8098')
}
if (Test-Path 'artifacts/body-edited.docx') {
  try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path 'artifacts/body-edited.docx'))
    try {
      $entry = $zip.GetEntry('word/document.xml')
      $reader = New-Object System.IO.StreamReader($entry.Open(), [System.Text.Encoding]::UTF8)
      try { $xml = $reader.ReadToEnd() } finally { $reader.Dispose() }
      $checks['new_marker_present'] = $xml.Contains('NEW_BODY_VALUE')
      $checks['old_marker_absent'] = -not $xml.Contains('OLD_BODY_VALUE')
      $checks['table_preserved'] = $xml.Contains('TABLE_KEEP_OK')
    } finally { $zip.Dispose() }
  } catch { $checks['docx_opens'] = $false }
} else { $checks['docx_opens'] = $false }
$checks | ConvertTo-Json -Compress
if ($checks.Values -contains $false) { exit 1 }
exit 0
