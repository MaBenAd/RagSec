param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendReadyUrl = "http://127.0.0.1:8000/healthz"
$backendDocsUrl = "http://127.0.0.1:8000/docs"
$frontendUrl = "http://127.0.0.1:3000/login"
$logDir = Join-Path $root "backend\data\logs"
$backendProcess = $null
$frontendProcess = $null

function Get-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @($py.Source, "-3")
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @($python.Source)
    }

    throw "Python is required but was not found in PATH."
}

function Ensure-EnvFile {
    $envPath = Join-Path $root ".env"
    $examplePath = Join-Path $root ".env.example"

    if (-not (Test-Path $envPath)) {
        Copy-Item -LiteralPath $examplePath -Destination $envPath
        Write-Warning ".env was missing. A copy of .env.example has been created for you."
    }
}

function Ensure-Venv {
    $pythonExe = Join-Path $root "venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        return $pythonExe
    }

    Write-Host "Creating virtual environment..."
    $pythonCommand = Get-PythonCommand
    $pythonArgs = @()
    if ($pythonCommand.Length -gt 1) {
        $pythonArgs += $pythonCommand[1..($pythonCommand.Length - 1)]
    }
    $pythonArgs += @("-m", "venv", (Join-Path $root "venv"))
    & $pythonCommand[0] @pythonArgs

    if (-not (Test-Path $pythonExe)) {
        throw "Virtual environment creation failed."
    }

    return $pythonExe
}

function Ensure-BackendDependencies {
    param([string]$PythonExe)

    $imports = "import uvicorn, dotenv, sqlalchemy, alembic"
    & $PythonExe -c $imports *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    Write-Host "Installing backend dependencies..."
    & $PythonExe -m pip install -r (Join-Path $root "requirements.txt")
}

function Wait-ForUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$MaxSeconds = 90
    )

    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    Write-Warning "$Label is not ready after $MaxSeconds seconds."
    return $false
}

function Test-UrlReady {
    param([Parameter(Mandatory = $true)][string]$Url)

    try {
        $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $true
    }
    catch {
        return $false
    }
}

function Test-UrlReadyWithGrace {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$MaxSeconds = 10
    )

    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        if (Test-UrlReady -Url $Url) {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Stop-ChildProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

function Stop-DockerAppServices {
    try {
        docker compose stop backend frontend *> $null
    }
    catch {
    }
}

function Stop-ProcessOnPort {
    param([int]$Port)

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if (-not $listeners) {
            return
        }

        $processIds = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($processId in $processIds) {
            if (-not $processId -or $processId -eq $PID) {
                continue
            }

            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($null -eq $process) {
                continue
            }

            if ($process.ProcessName -like "*docker*") {
                Write-Warning "Port $Port is owned by a Docker-related process ($($process.ProcessName))."
                continue
            }

            Write-Host "Stopping existing process on port $Port (PID $processId / $($process.ProcessName))..."
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
    catch {
        Write-Warning "Unable to inspect port $Port. Continuing startup."
    }
}

try {
    Set-Location $root
    Ensure-EnvFile
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null

    Write-Host "Starting Chatbot USMS development environment..."

    $pythonExe = Ensure-Venv

    $null = Get-Command npm.cmd -ErrorAction Stop
    $null = Get-Command docker -ErrorAction Stop
    docker info *> $null

    Ensure-BackendDependencies -PythonExe $pythonExe

    $env:PYTHONPATH = $root
    if (-not $env:QDRANT_URL) {
        $env:QDRANT_URL = "http://127.0.0.1:6333"
    }
    if (-not $env:RAG_EMBEDDING_BACKEND) {
        $env:RAG_EMBEDDING_BACKEND = "hash"
    }
    if (-not $env:ENABLE_EMOTION_LLM) {
        $env:ENABLE_EMOTION_LLM = "false"
    }
    if (-not $env:ENABLE_EDT_LLM) {
        $env:ENABLE_EDT_LLM = "false"
    }
    if (-not $env:ENABLE_TITLE_LLM) {
        $env:ENABLE_TITLE_LLM = "false"
    }
    $env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"

    Write-Host "Starting Docker infrastructure (postgres, redis, qdrant)..."
    docker compose up -d postgres redis qdrant --wait
    Stop-DockerAppServices

    Write-Host "Bootstrapping shared dev content..."
    & $pythonExe "backend/scripts/bootstrap_dev_content.py"

    Stop-ProcessOnPort -Port 8000
    Stop-ProcessOnPort -Port 3000

    Write-Host "Starting backend on $backendDocsUrl"
    $backendProcess = Start-Process -FilePath $pythonExe -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $root -RedirectStandardOutput (Join-Path $logDir "dev-backend.out.log") -RedirectStandardError (Join-Path $logDir "dev-backend.err.log") -PassThru

    $frontendDir = Join-Path $root "frontend"
    if (-not (Test-Path $frontendDir)) {
        throw "Frontend directory not found: $frontendDir"
    }

    if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies..."
        Push-Location $frontendDir
        npm install
        Pop-Location
    }

    Write-Host "Starting frontend on $frontendUrl"
    $frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000") -WorkingDirectory $frontendDir -RedirectStandardOutput (Join-Path $logDir "dev-frontend.out.log") -RedirectStandardError (Join-Path $logDir "dev-frontend.err.log") -PassThru

    Write-Host "Waiting for services to be ready..."
    [void](Wait-ForUrl -Url $backendReadyUrl -Label "Backend")
    [void](Wait-ForUrl -Url $frontendUrl -Label "Frontend")

    if (-not $NoBrowser) {
        Write-Host "Opening browser..."
        try {
            Start-Process -FilePath "explorer.exe" -ArgumentList $frontendUrl | Out-Null
        }
        catch {
            Write-Warning "Unable to open browser automatically. Open $frontendUrl manually."
        }
    }

    Write-Host "Services are running."
    Write-Host "Frontend: $frontendUrl"
    Write-Host "Backend docs: $backendDocsUrl"
    Write-Host "Press Ctrl+C to stop local frontend/backend. Docker infra will stay up."

    while ($true) {
        $backendStopped = $false
        $frontendStopped = $false

        if ($null -ne $backendProcess -and $backendProcess.HasExited) {
            $backendStopped = -not (Test-UrlReadyWithGrace -Url $backendReadyUrl)
        }

        if ($null -ne $frontendProcess -and $frontendProcess.HasExited) {
            $frontendStopped = -not (Test-UrlReadyWithGrace -Url $frontendUrl)
        }

        if ($backendStopped -or $frontendStopped) {
            Write-Warning "One service stopped. Shutting down the other local service."
            break
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host "Stopping local frontend/backend..."
    Stop-ChildProcess -Process $backendProcess
    Stop-ChildProcess -Process $frontendProcess
    Stop-ProcessOnPort -Port 8000
    Stop-ProcessOnPort -Port 3000
}
