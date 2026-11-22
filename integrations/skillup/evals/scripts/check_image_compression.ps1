$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.Drawing
function Entries([string]$Path) {
  $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $Path))
  try {
    $result = @{}
    foreach ($entry in $zip.Entries) {
      $stream = $entry.Open()
      try {
        $memory = New-Object System.IO.MemoryStream
        $stream.CopyTo($memory)
        $result[$entry.FullName] = $memory.ToArray()
        $memory.Dispose()
      } finally { $stream.Dispose() }
    }
    return $result
  } finally { $zip.Dispose() }
}
function ImageInfo([byte[]]$Bytes) {
  $memory = [System.IO.MemoryStream]::new($Bytes)
  $image = [System.Drawing.Image]::FromStream($memory)
  try {
    return @{ Width = $image.Width; Height = $image.Height;
              Alpha = [System.Drawing.Image]::IsAlphaPixelFormat($image.PixelFormat) }
  } finally { $image.Dispose(); $memory.Dispose() }
}
function MediaEntries($Entries) {
  $media = @{}
  foreach ($item in $Entries.GetEnumerator()) {
    if ($item.Key -like 'word/media/*') { $media[$item.Key] = $item.Value }
  }
  return $media
}
$checks = [ordered]@{ exit_zero = ($env:EVAL_EXIT_CODE -eq '0') }
$sourceHash = (Get-FileHash 'fixtures/word-image.docx' -Algorithm SHA256).Hash.ToLower()
$checks['input_unchanged'] = ($sourceHash -eq 'e088a0b113a61d991ac33aae4b1bde9dcf46669b951a9dbe7313e8d9043d9fa9')
if (Test-Path 'artifacts/compressed.docx') {
  try {
    $before = Entries 'fixtures/word-image.docx'
    $after = Entries 'artifacts/compressed.docx'
    $checks['docx_opens'] = ($after.ContainsKey('word/document.xml'))
    $checks['document_xml_unchanged'] = ([Convert]::ToBase64String($before['word/document.xml']) -ceq [Convert]::ToBase64String($after['word/document.xml']))
    $beforeMedia = MediaEntries $before
    $afterMedia = MediaEntries $after
    $beforeBytes = 0; foreach ($item in $beforeMedia.Values) { $beforeBytes += $item.Length }
    $afterBytes = 0; foreach ($item in $afterMedia.Values) { $afterBytes += $item.Length }
    $checks['media_smaller'] = ($afterBytes -lt $beforeBytes)
    $checks['package_smaller'] = ((Get-Item 'artifacts/compressed.docx').Length -lt (Get-Item 'fixtures/word-image.docx').Length)
    $checks['images_decode'] = $true
    $checks['dimensions_preserved_or_scaled'] = $true
    $checks['alpha_preserved'] = $true
    if ($beforeMedia.Count -eq 0 -or $beforeMedia.Count -ne $afterMedia.Count) {
      $checks['images_decode'] = $false
      $checks['dimensions_preserved_or_scaled'] = $false
      $checks['alpha_preserved'] = $false
    } else {
      $afterByBase = @{}
      foreach ($name in $afterMedia.Keys) { $afterByBase[[IO.Path]::GetFileNameWithoutExtension($name)] = $name }
      foreach ($name in @($beforeMedia.Keys)) {
        $base = [IO.Path]::GetFileNameWithoutExtension($name)
        if (-not $afterByBase.ContainsKey($base)) {
          $checks['images_decode'] = $false
          $checks['dimensions_preserved_or_scaled'] = $false
          $checks['alpha_preserved'] = $false
          continue
        }
        $afterName = $afterByBase[$base]
        try {
          $beforeInfo = ImageInfo $beforeMedia[$name]
          $afterInfo = ImageInfo $afterMedia[$afterName]
        } catch {
          $checks['images_decode'] = $false
          $checks['dimensions_preserved_or_scaled'] = $false
          $checks['alpha_preserved'] = $false
          continue
        }
        $expectedWidth = [Math]::Min($beforeInfo.Width, 1600)
        $expectedHeight = $beforeInfo.Height
        if ($beforeInfo.Width -gt 1600) {
          $expectedHeight = [int][Math]::Round($beforeInfo.Height * 1600 / $beforeInfo.Width)
        }
        if ($afterInfo.Width -ne $expectedWidth -or $afterInfo.Height -ne $expectedHeight) {
          $checks['dimensions_preserved_or_scaled'] = $false
        }
        if ($beforeInfo.Alpha -and (-not $afterInfo.Alpha -or [IO.Path]::GetExtension($afterName) -ne '.png')) {
          $checks['alpha_preserved'] = $false
        }
      }
    }
  } catch {
    $checks['docx_opens'] = $false
  }
} else {
  $checks['docx_opens'] = $false
}
$checks | ConvertTo-Json -Compress
if ($checks.Values -contains $false) { exit 1 }
exit 0
