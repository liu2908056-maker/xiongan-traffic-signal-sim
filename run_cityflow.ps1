param([string]$Period="morning", [int]$Steps=7500, [string]$Algorithm="max_pressure", [string]$FlowFile="")
$ErrorActionPreference = "Stop"
docker build -t xiong-an-cityflow:local .
$arguments = @("--period", $Period, "--algorithm", $Algorithm, "--steps", $Steps, "--threads", "1")
if ($FlowFile) { $arguments += @("--flow-file", $FlowFile) }
docker run --rm -v "${PWD}\outputs:/app/outputs" xiong-an-cityflow:local @arguments
