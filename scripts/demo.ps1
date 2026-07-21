$ErrorActionPreference = "Stop"

Write-Host "Building and starting API, dashboard, and MCP services..."
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }

$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$dashboardPort = if ($env:DASHBOARD_PORT) { $env:DASHBOARD_PORT } else { "8501" }
$mcpPort = if ($env:MCP_PORT) { $env:MCP_PORT } else { "8001" }

Write-Host "Waiting for the API health endpoint..."
function Wait-HttpHealth {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Service
    )
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            Invoke-RestMethod -Uri $Uri -TimeoutSec 3 | Out-Null
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Host "$Service did not become healthy. Recent logs:"
    docker compose logs --tail 80 $Service
    throw "$Service health check timed out"
}

Wait-HttpHealth -Uri "http://localhost:$apiPort/health" -Service "api"
Wait-HttpHealth -Uri "http://localhost:$dashboardPort/_stcore/health" -Service "dashboard"

$mcpRunning = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $runningServices = @(docker compose ps --status running --services mcp)
    if ($LASTEXITCODE -eq 0 -and $runningServices -contains "mcp") {
        $mcpRunning = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $mcpRunning) {
    Write-Host "MCP service is not running. Recent logs:"
    docker compose logs --tail 80 mcp
    throw "MCP startup check timed out"
}

Write-Host "Demo is ready."
Write-Host "Dashboard: http://localhost:$dashboardPort"
Write-Host "API docs: http://localhost:$apiPort/docs"
Write-Host "MCP endpoint: http://localhost:$mcpPort/mcp"
Write-Host "Follow docs/demo-script.md for the 3-5 minute walkthrough."
Write-Host "Stop with: docker compose down"
