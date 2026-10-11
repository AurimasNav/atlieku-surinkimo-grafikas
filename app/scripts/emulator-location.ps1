<#
.SYNOPSIS
  Feeds this PC's location (from Windows location services) to the Android emulator.

.DESCRIPTION
  The emulator has no access to the PC's location by itself. Windows estimates the PC's
  position from nearby Wi-Fi networks (usually within 50-200 m); this script reads it and
  sends it to the running emulator with `adb emu geo fix`, repeating every two seconds,
  because the emulator only applies positions while an app is listening.

  Requires Windows Settings > Privacy & security > Location to be on, including access for
  desktop apps.

.EXAMPLE
  ./scripts/emulator-location.ps1               # feed the PC's location for 2 minutes
  ./scripts/emulator-location.ps1 -Seconds 600
  ./scripts/emulator-location.ps1 -Latitude 54.7692 -Longitude 25.1840   # a fixed position
#>
param(
  [int]$Seconds = 120,
  [double]$Latitude = [double]::NaN,
  [double]$Longitude = [double]::NaN
)

$ErrorActionPreference = 'Stop'
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
if (-not (Test-Path $adb)) { $adb = 'adb' }

if ([double]::IsNaN($Latitude) -or [double]::IsNaN($Longitude)) {
  Add-Type -AssemblyName System.Device
  $watcher = New-Object System.Device.Location.GeoCoordinateWatcher([System.Device.Location.GeoPositionAccuracy]::High)
  if (-not $watcher.TryStart($false, [TimeSpan]::FromSeconds(15))) {
    throw 'Windows location is unavailable. Turn on Settings > Privacy & security > Location (and access for desktop apps).'
  }
  $deadline = (Get-Date).AddSeconds(15)
  while ($watcher.Position.Location.IsUnknown -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
  $location = $watcher.Position.Location
  $watcher.Stop()
  if ($location.IsUnknown) { throw 'Windows did not return a location in time.' }
  $Latitude = $location.Latitude
  $Longitude = $location.Longitude
  Write-Host ("Windows location: ±{0:N0} m" -f $location.HorizontalAccuracy)
}

$culture = [System.Globalization.CultureInfo]::InvariantCulture
$lat = $Latitude.ToString('0.000000', $culture)
$lon = $Longitude.ToString('0.000000', $culture)
Write-Host "Sending $lat, $lon to the emulator for $Seconds s (Ctrl+C to stop)..."
$end = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $end) {
  # Note the order: longitude first, then latitude.
  & $adb emu geo fix $lon $lat | Out-Null
  Start-Sleep -Seconds 2
}
