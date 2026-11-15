param([string]$AndroidJar = 'D:\RemWorkspace\tools\android-sdk\platforms\android-11\android.jar')
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$output = Join-Path $project 'out\java-check'
if (-not (Test-Path -LiteralPath $AndroidJar)) { throw 'Official Android 30 SDK android.jar is required.' }
New-Item -ItemType Directory -Path $output -Force | Out-Null
$sources = @(Get-ChildItem -LiteralPath (Join-Path $project 'vendor\rem\RemBody\src') -Recurse -Filter '*.java' | ForEach-Object FullName)
$deps = Join-Path $project 'vendor\rem\RemBody\libs\*'
& javac -encoding UTF-8 --release 8 -classpath "$AndroidJar;$deps" -d $output $sources
if ($LASTEXITCODE -ne 0) { throw 'Android source compilation failed.' }
& javac -encoding UTF-8 --release 8 -classpath $output -d $output (Join-Path $project 'tests\BodyStateTest.java') (Join-Path $project 'tests\ObservationPolicyTest.java')
if ($LASTEXITCODE -ne 0) { throw 'State test compilation failed.' }
& java -cp $output BodyStateTest
if ($LASTEXITCODE -ne 0) { throw 'State tests failed.' }
& java -cp $output ObservationPolicyTest
if ($LASTEXITCODE -ne 0) { throw 'Temporal observation tests failed.' }
Write-Output 'PASS: source compilation only; this is not a ROM build or phone hardware test.'
