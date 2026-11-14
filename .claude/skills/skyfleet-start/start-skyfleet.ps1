<#
.SYNOPSIS
  Starts (or reports on) the local SkyFleet development environment. Windows PowerShell 5.1.

.DESCRIPTION
  Docker Desktop -> PostgreSQL (docker compose, service "db") -> migration check (never applies
  migrations) -> FastAPI (8000) -> Simulation Worker -> Vite frontend (5173).

  Idempotent and non-destructive: healthy services are reused, nothing is killed or restarted,
  no volume/container is removed, no port is changed. A port held by something that is not
  SkyFleet is reported and that step stops.

  Each started service runs in its own minimized console window (close it to stop that service)
  and appends its output to a log file under %LOCALAPPDATA%\SkyFleet\logs.

.PARAMETER StatusOnly
  Detect and report only; start nothing (not even Docker Desktop).
#>
[CmdletBinding()]
param(
    [switch]$StatusOnly,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$DockerExe = 'docker',
    [string]$DockerDesktopPath = 'C:\Program Files\Docker\Docker\Docker Desktop.exe',
    [string]$LogDir = (Join-Path $env:LOCALAPPDATA 'SkyFleet\logs'),
    [int]$DockerWaitSeconds = 180,
    [int]$ServiceWaitSeconds = 60
)

$ErrorActionPreference = 'Continue'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://localhost:$FrontendPort"

$Report = New-Object System.Collections.ArrayList
function Add-Step([string]$Name, [string]$State, [string]$Detail) {
    [void]$Report.Add([pscustomobject]@{ Step = $Name; State = $State; Detail = $Detail })
    Write-Host ("[{0,-8}] {1}: {2}" -f $State, $Name, $Detail)
}

# --- helpers ---------------------------------------------------------------------------------

# Runs a command line through cmd.exe so native stderr never becomes a PowerShell error.
function Invoke-Quiet([string]$CommandLine) {
    $null = & cmd.exe /c "$CommandLine >nul 2>&1"
    return $LASTEXITCODE
}
function Invoke-Capture([string]$CommandLine) {
    return (& cmd.exe /c "$CommandLine 2>nul")
}

function Test-DockerEngine {
    return ((Invoke-Quiet "`"$DockerExe`" info") -eq 0)
}

function Get-Listener([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $c) { return $null }
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    return [pscustomobject]@{ Pid = $c.OwningProcess; Name = if ($p) { $p.ProcessName } else { '?' } }
}

function Get-Http([string]$Url, [int]$TimeoutSec = 3) {
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop }
    catch { return $null }
}

function Test-SkyFleetBackend {
    $r = Get-Http "$BackendUrl/openapi.json"
    if (-not $r) { return $false }
    try { return (($r.Content | ConvertFrom-Json).info.title -eq 'SkyFleet API') } catch { return $false }
}

function Test-SkyFleetFrontend {
    $r = Get-Http "$FrontendUrl/"
    return ($r -and $r.Content -match '<title>SkyFleet')
}

# True only when the API reports a live worker. `worker_stale` (GET /api/flights) exists in every
# version; when the response also carries the Feature 020 `simulation` block, its `worker_running`
# must agree. Returns $null when the API cannot be read.
function Get-WorkerHealth {
    $r = Get-Http "$BackendUrl/api/flights" 5
    if (-not $r) { return $null }
    try { $f = $r.Content | ConvertFrom-Json } catch { return $null }
    if ($null -eq $f.worker_stale) { return $null }
    $running = ($f.worker_stale -eq $false)
    $speed = $null
    if ($f.simulation) {
        $running = $running -and ($f.simulation.worker_running -eq $true)
        $speed = $f.simulation.speed
    }
    return [pscustomobject]@{ Running = $running; Speed = $speed }
}
function Test-WorkerFresh { $h = Get-WorkerHealth; return [bool]($h -and $h.Running) }

# Worker processes: command line mentions app.worker (uv / python / cmd launcher), not this script.
function Get-WorkerProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.ProcessId -ne $PID -and $_.Name -match '^(python|pythonw|uv|cmd)(\.exe)?$' -and
            $_.CommandLine -match 'app\.worker'
        }
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Condition) { return $true }
        Start-Sleep -Seconds 2
    }
    return [bool](& $Condition)
}

# Starts a long-running service in its own minimized console window that outlives this script.
function Start-Service-Window([string]$Title, [string]$WorkDir, [string]$Command, [string]$LogName) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $log = Join-Path $LogDir $LogName
    $line = "title $Title & $Command >> `"$log`" 2>&1"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $line -WorkingDirectory $WorkDir `
        -WindowStyle Minimized | Out-Null
    return $log
}

# --- 1-2. Docker engine -----------------------------------------------------------------------
$dockerOk = $false
if (Test-DockerEngine) {
    $dockerOk = $true
    Add-Step 'Docker' 'OK' 'engine is running'
}
elseif ($StatusOnly) {
    Add-Step 'Docker' 'DOWN' 'engine is not running (status only: nothing started)'
}
elseif (-not (Test-Path -LiteralPath $DockerDesktopPath)) {
    Add-Step 'Docker' 'FAILED' "engine not running and Docker Desktop not found at '$DockerDesktopPath'. Install or start it manually."
}
else {
    if (-not (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $DockerDesktopPath | Out-Null
    }
    if (Wait-Until { Test-DockerEngine } $DockerWaitSeconds) {
        $dockerOk = $true
        Add-Step 'Docker' 'STARTED' 'Docker Desktop started; engine is ready'
    }
    else {
        Add-Step 'Docker' 'FAILED' "engine not ready after $DockerWaitSeconds s. Open Docker Desktop and check it, then run again."
    }
}

# --- 3-4. PostgreSQL --------------------------------------------------------------------------
$dbOk = $false
if ($dockerOk) {
    $cid = (Invoke-Capture "`"$DockerExe`" compose -f `"$ComposeFile`" ps -q db" | Select-Object -First 1)
    $health = if ($cid) { (Invoke-Capture "`"$DockerExe`" inspect --format {{.State.Health.Status}} $cid" | Select-Object -First 1) } else { '' }
    if ($health -eq 'healthy') {
        $dbOk = $true
        Add-Step 'PostgreSQL' 'OK' 'service "db" healthy on localhost:55432'
    }
    elseif ($StatusOnly) {
        Add-Step 'PostgreSQL' 'DOWN' "service \"db\" not healthy (status: '$health'); status only: nothing started"
    }
    else {
        # up -d only creates/starts the service; it never removes containers or volumes.
        $code = Invoke-Quiet "`"$DockerExe`" compose -f `"$ComposeFile`" up -d db"
        if ($code -ne 0) {
            Add-Step 'PostgreSQL' 'FAILED' 'docker compose up -d db failed (port 55432 busy? check "docker compose ps")'
        }
        else {
            $ready = Wait-Until {
                $id = (Invoke-Capture "`"$DockerExe`" compose -f `"$ComposeFile`" ps -q db" | Select-Object -First 1)
                $id -and ((Invoke-Capture "`"$DockerExe`" inspect --format {{.State.Health.Status}} $id" | Select-Object -First 1) -eq 'healthy')
            } $ServiceWaitSeconds
            if ($ready) { $dbOk = $true; Add-Step 'PostgreSQL' 'STARTED' 'service "db" is healthy on localhost:55432' }
            else { Add-Step 'PostgreSQL' 'FAILED' "not healthy after $ServiceWaitSeconds s (see: docker compose logs db)" }
        }
    }
}
else {
    Add-Step 'PostgreSQL' 'SKIPPED' 'Docker engine is not available'
}

# --- 5. Migration revision (read-only; never upgrades) ----------------------------------------
$schemaOk = $false
if ($dbOk) {
    if (-not (Test-Path (Join-Path $BackendDir '.venv'))) {
        Add-Step 'Migrations' 'FAILED' 'backend\.venv not found. Create it first (cd backend; uv sync).'
    }
    else {
        Push-Location $BackendDir
        try {
            $headsOut = Invoke-Capture 'uv run --no-sync alembic heads'
            $currentOut = Invoke-Capture 'uv run --no-sync alembic current'
        }
        finally { Pop-Location }
        $head = if (($headsOut | Out-String) -match '(?m)^(\S+)\s+\(head\)') { $Matches[1] } else { $null }
        $current = if (($currentOut | Out-String) -match '(?m)^([0-9A-Za-z_]+)') { $Matches[1] } else { $null }
        if (-not $head) {
            Add-Step 'Migrations' 'FAILED' 'could not read the Alembic head (is the backend .venv healthy?)'
        }
        elseif ($current -eq $head) {
            $schemaOk = $true
            Add-Step 'Migrations' 'OK' "database is at head ($head)"
        }
        else {
            $shown = if ($current) { $current } else { 'none' }
            Add-Step 'Migrations' 'OUTDATED' "database is at '$shown', code expects '$head'. NOT applied automatically. Review, then run: cd backend; uv run alembic upgrade head"
        }
    }
}
else {
    Add-Step 'Migrations' 'SKIPPED' 'PostgreSQL is not healthy'
}

# --- 6-7. FastAPI -----------------------------------------------------------------------------
$apiOk = $false
$listener = Get-Listener $BackendPort
if ($listener) {
    if (Test-SkyFleetBackend) {
        $apiOk = $true
        Add-Step 'API' 'OK' "SkyFleet API already running at $BackendUrl (pid $($listener.Pid)); reused"
    }
    else {
        Add-Step 'API' 'CONFLICT' "port $BackendPort is held by '$($listener.Name)' (pid $($listener.Pid)), which is not a healthy SkyFleet API. Not killed; free the port and run again."
    }
}
elseif ($StatusOnly) {
    Add-Step 'API' 'DOWN' "nothing listens on $BackendPort"
}
elseif (-not $schemaOk) {
    Add-Step 'API' 'SKIPPED' 'database not ready or schema not at head'
}
else {
    $log = Start-Service-Window 'SkyFleet API' $BackendDir "uv run --no-sync uvicorn app.main:app --reload --host 127.0.0.1 --port $BackendPort" 'api.log'
    if (Wait-Until { Test-SkyFleetBackend } $ServiceWaitSeconds) {
        $apiOk = $true
        Add-Step 'API' 'STARTED' "$BackendUrl (log: $log)"
    }
    else { Add-Step 'API' 'FAILED' "no healthy answer after $ServiceWaitSeconds s (log: $log)" }
}

# --- 8-9. Simulation Worker -------------------------------------------------------------------
$workerFresh = $false
$procs = @(Get-WorkerProcesses)
if (-not $apiOk) {
    $why = if ($procs.Count -gt 0) { "worker process present (pid $($procs[0].ProcessId)), " } else { '' }
    Add-Step 'Worker' 'SKIPPED' "${why}heartbeat cannot be verified without a healthy API"
}
else {
    $health = Get-WorkerHealth
    $workerFresh = [bool]($health -and $health.Running)
    if ($workerFresh) {
        Add-Step 'Worker' 'OK' "heartbeat fresh$(if ($null -ne $health.Speed) { " (speed $($health.Speed)x)" }); reused"
    }
    elseif ($procs.Count -gt 0) {
        # A worker process exists: give its heartbeat a moment, but never start a second one.
        $workerFresh = Wait-Until { Test-WorkerFresh } 15
        if ($workerFresh) { Add-Step 'Worker' 'OK' 'process running, heartbeat became fresh; reused' }
        else { Add-Step 'Worker' 'STALE' "process (pid $($procs[0].ProcessId)) exists but the heartbeat is not fresh. Not restarted; inspect its window/log, stop it yourself if hung, then run again." }
    }
    elseif ($StatusOnly) {
        Add-Step 'Worker' 'DOWN' 'no worker process and no fresh heartbeat'
    }
    elseif (-not $schemaOk) {
        Add-Step 'Worker' 'SKIPPED' 'schema not at head'
    }
    else {
        $log = Start-Service-Window 'SkyFleet Worker' $BackendDir 'uv run --no-sync python -m app.worker' 'worker.log'
        $workerFresh = Wait-Until { Test-WorkerFresh } $ServiceWaitSeconds
        if ($workerFresh) { Add-Step 'Worker' 'STARTED' "heartbeat fresh (log: $log)" }
        else { Add-Step 'Worker' 'FAILED' "no fresh heartbeat after $ServiceWaitSeconds s (log: $log)" }
    }
}

# --- 10. Frontend -----------------------------------------------------------------------------
$feOk = $false
$listener = Get-Listener $FrontendPort
if ($listener) {
    if (Test-SkyFleetFrontend) {
        $feOk = $true
        Add-Step 'Frontend' 'OK' "SkyFleet frontend already running at $FrontendUrl (pid $($listener.Pid)); reused"
    }
    else {
        Add-Step 'Frontend' 'CONFLICT' "port $FrontendPort is held by '$($listener.Name)' (pid $($listener.Pid)), which is not the SkyFleet frontend. Not killed; free the port and run again."
    }
}
elseif ($StatusOnly) {
    Add-Step 'Frontend' 'DOWN' "nothing listens on $FrontendPort"
}
elseif (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Add-Step 'Frontend' 'FAILED' 'frontend\node_modules not found. Run: cd frontend; npm install (not done automatically).'
}
else {
    # --strictPort: if the port is taken Vite fails instead of silently choosing another one.
    $log = Start-Service-Window 'SkyFleet Frontend' $FrontendDir "npm run dev -- --port $FrontendPort --strictPort" 'frontend.log'
    if (Wait-Until { Test-SkyFleetFrontend } $ServiceWaitSeconds) {
        $feOk = $true
        Add-Step 'Frontend' 'STARTED' "$FrontendUrl (log: $log)"
    }
    else { Add-Step 'Frontend' 'FAILED' "no answer after $ServiceWaitSeconds s (log: $log)" }
}

# --- 11-12. Final report ----------------------------------------------------------------------
Write-Host ''
Write-Host '=== SkyFleet environment ==='
$Report | ForEach-Object { Write-Host ("{0,-11} {1,-9} {2}" -f $_.Step, $_.State, $_.Detail) }
Write-Host ''
Write-Host "Frontend: $FrontendUrl    API docs: $BackendUrl/docs"
Write-Host "Logs:     $LogDir  (Get-Content <file> -Wait -Tail 50)"
$allGood = $dockerOk -and $dbOk -and $schemaOk -and $apiOk -and $workerFresh -and $feOk
if ($allGood) { Write-Host 'RESULT: all services are up.'; exit 0 }
Write-Host 'RESULT: NOT all services are up; see the states above.'
exit 1
