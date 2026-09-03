param([string]$Period="morning", [int]$Steps=7500, [string]$Algorithm="max_pressure", [string]$FlowFile="")
$ErrorActionPreference = "Stop"
$image = "xiong-an-cityflow:submission"
$existing = docker image inspect $image 2>$null
if ($LASTEXITCODE -ne 0 -or -not $existing) {
    docker load -i ".\docker\xiong-an-cityflow-submission.tar"
}
$arguments = @("--period", $Period, "--algorithm", $Algorithm, "--steps", $Steps, "--threads", "1")
if ($FlowFile) { $arguments += @("--flow-file", $FlowFile) }
docker run --rm -v "${PWD}\outputs:/app/outputs" $image @arguments
