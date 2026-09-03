param(
    [ValidateSet('ugat_frap', 'ugat_frap_transyt', 'transyt', 'max_pressure', 'fixed')][string]$Algorithm = 'ugat_frap_transyt',
    [ValidateSet('morning', 'midday', 'evening')][string]$Period = 'morning',
    [int]$Steps = 7500,
    [int]$Threads = 4,
    [int]$VisualDelayMs = 0,
    [int]$LiveInterval = 10,
    [string]$Image = 'xiong-an-20-platform:final'
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $ProjectRoot
try {
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Image $Image is missing. Building the CityFlow image..." -ForegroundColor Yellow
        docker build -t $Image .
        if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
    }
    # A unique stream avoids a stale monitor retaining the read offset from a
    # previous run whose trace file was overwritten.
    $RunId = Get-Date -Format 'yyyyMMdd_HHmmss'
    $LiveTrace = Join-Path $ProjectRoot "outputs\live_$($Algorithm)_$($Period)_$RunId.jsonl"
    $LiveTraceName = Split-Path -Leaf $LiveTrace
    $Monitor = Start-Process -FilePath python -ArgumentList @('.\src\show_live.py', $LiveTrace, '--roadnet', '.\data\xiong_an_20\roadnet.json', '--topology', '.\data\xiong_an_20\topology.json') -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    docker run --rm -v "${ProjectRoot}:/workspace/final" --entrypoint /bin/bash $Image -lc "cd /workspace/final && python src/run_cityflow.py --period $Period --algorithm $Algorithm --steps $Steps --threads $Threads --live-interval $LiveInterval --visual-delay-ms $VisualDelayMs --live-trace /workspace/final/outputs/$LiveTraceName"
    if ($LASTEXITCODE -ne 0) { throw 'CityFlow simulation failed.' }
} finally {
    Pop-Location
}
