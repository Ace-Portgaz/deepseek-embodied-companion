param([int]$MinimumFreeGiB = 40)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$driveRoot = [System.IO.Path]::GetPathRoot($project)
$drive = [System.IO.DriveInfo]::new($driveRoot)
$free = [Math]::Round($drive.AvailableFreeSpace / 1GB, 1)
[pscustomobject]@{
    PhysicalDrive = $driveRoot
    FreeGiB = $free
    MinimumFreeGiB = $MinimumFreeGiB
    ReadyToStartWithContinuousMonitoring = ($free -ge $MinimumFreeGiB)
    RecommendedUnconstrainedFreeGiB = 300
    Note = '300 GiB is planning guidance, not a hard requirement. Starting above the minimum does not guarantee the whole build fits. Use the continuous space guard.'
}
if ($free -lt $MinimumFreeGiB) {
    throw "Full Android source download is blocked: $driveRoot has $free GiB free."
}
