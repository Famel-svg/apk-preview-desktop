$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$compiler = "$env:SystemRoot\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw "C# compiler not found: $compiler"
}

$outputDirectory = Join-Path $projectRoot "dist\APK Preview Desktop"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
$executable = Join-Path $outputDirectory "APK Preview Desktop.exe"
$source = Join-Path $projectRoot "native\DesktopLauncher.cs"
$bridge = Join-Path $projectRoot "native\ProcessBridge.exe"
$bridgeSource = Join-Path $projectRoot "native\ProcessBridge.cs"

& $compiler /nologo /target:winexe /optimize+ /out:$executable $source
if ($LASTEXITCODE -ne 0) {
    throw "C# launcher build failed with exit code $LASTEXITCODE"
}

& $compiler /nologo /target:winexe /optimize+ /out:$bridge $bridgeSource
if ($LASTEXITCODE -ne 0) {
    throw "C# process bridge build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Executable not produced: $executable"
}
if (-not (Test-Path -LiteralPath $bridge -PathType Leaf)) {
    throw "Process bridge not produced: $bridge"
}
Write-Output $executable
