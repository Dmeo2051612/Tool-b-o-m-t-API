param(
    [string]$GatewayProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TestRedisUrl = "redis://127.0.0.1:6379/15",
    [int]$RateLimitPort = 8082,
    [int]$FailClosedPort = 8083,
    [int]$UnavailableRedisPort = 6399
)

# Integration tests for rate limiting and Redis fail-closed behavior.
# Starts temporary Flask app.py instances and always attempts to stop them.
# The existing Gateway on 8081 is not modified or restarted.
$ErrorActionPreference = "Stop"
$script:Results = @()
$script:Processes = @()
$script:LogDirectory = Join-Path $env:TEMP ("finora-gateway-integration-v3-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $script:LogDirectory -Force | Out-Null

function Add-Result {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $label = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    $script:Results += [pscustomobject]@{ Test = $Name; Result = $label; Detail = $Detail }
    Write-Host ("[{0}] {1} - {2}" -f $label, $Name, $Detail) -ForegroundColor $color
}

function Test-TcpPortOpen {
    param([string]$HostName = "127.0.0.1", [int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(300)) { return $false }
        $client.EndConnect($async)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Invoke-Probe {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][ValidateSet("GET", "POST")][string]$Method,
        [hashtable]$Headers = @{},
        [string]$Body
    )
    $request = [System.Net.HttpWebRequest]::Create($Url)
    $request.Method = $Method
    $request.Timeout = 4000
    $request.ReadWriteTimeout = 4000
    $request.AllowAutoRedirect = $false
    $request.KeepAlive = $false

    foreach ($key in $Headers.Keys) {
        if ($key -ieq "Content-Type") { $request.ContentType = [string]$Headers[$key] }
        else { $request.Headers[$key] = [string]$Headers[$key] }
    }

    if ($PSBoundParameters.ContainsKey("Body")) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
        $request.ContentLength = $bytes.Length
        if (-not $request.ContentType) { $request.ContentType = "application/json" }
        $stream = $request.GetRequestStream()
        try { $stream.Write($bytes, 0, $bytes.Length) }
        finally { $stream.Dispose() }
    }

    $response = $null
    try { $response = $request.GetResponse() }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) { $response = $_.Exception.Response }
        else { return [pscustomobject]@{ StatusCode = 0; Headers = $null; Body = $_.Exception.Message } }
    }
    try {
        $reader = New-Object -TypeName System.IO.StreamReader -ArgumentList $response.GetResponseStream()
        try { $responseBody = $reader.ReadToEnd() }
        finally { $reader.Dispose() }
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Headers = $response.Headers; Body = $responseBody }
    }
    finally { if ($response) { $response.Dispose() } }
}

function Start-TemporaryGateway {
    param([string]$Name, [int]$Port, [hashtable]$Environment)
    $python = Get-Command python.exe -ErrorAction Stop | Select-Object -First 1
    $logOut = Join-Path $script:LogDirectory "$Name.stdout.log"
    $logErr = Join-Path $script:LogDirectory "$Name.stderr.log"
    $variableNames = @("REDIS_URL", "PORT", "MAX_REQUESTS", "TIME_WINDOW", "TRUSTED_X_FOR_COUNT", "TRUSTED_X_PROTO_COUNT")
    $previous = @{}
    foreach ($nameToSet in $variableNames) {
        $previous[$nameToSet] = [Environment]::GetEnvironmentVariable($nameToSet, "Process")
    }
    try {
        foreach ($nameToSet in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($nameToSet, [string]$Environment[$nameToSet], "Process")
        }
        $proc = Start-Process -FilePath $python.Source -ArgumentList @("app.py") -WorkingDirectory $GatewayProjectPath -PassThru -WindowStyle Hidden -RedirectStandardOutput $logOut -RedirectStandardError $logErr
        $script:Processes += $proc
        return [pscustomobject]@{ Process = $proc; Port = $Port; Stdout = $logOut; Stderr = $logErr }
    }
    finally {
        foreach ($nameToSet in $variableNames) {
            [Environment]::SetEnvironmentVariable($nameToSet, $previous[$nameToSet], "Process")
        }
    }
}

function Wait-ForPort {
    param([int]$Port, [int]$TimeoutSeconds = 10)
    $until = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $until) {
        if (Test-TcpPortOpen -Port $Port) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Stop-TemporaryProcesses {
    foreach ($proc in @($script:Processes)) {
        try {
            $proc.Refresh()
            if (-not $proc.HasExited) {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                $proc.WaitForExit(3000) | Out-Null
            }
        }
        catch { }
    }
}

Write-Host "Finora Gateway resilience integration tests" -ForegroundColor Cyan
Write-Host "Gateway project: $GatewayProjectPath"
Write-Host "Temporary rate-limit Gateway: http://127.0.0.1:$RateLimitPort"
Write-Host "Temporary fail-closed Gateway: http://127.0.0.1:$FailClosedPort"
Write-Host "Rate-limit Redis DB: $TestRedisUrl"
Write-Host "Logs: $script:LogDirectory"
Write-Host "Safety: does not alter the existing Gateway on 8081 and does not delete Redis keys."
Write-Host "Note: the rate-limit test creates one temporary counter key in DB 15 (or the configured DB); TTL is 10 seconds."
Write-Host ""

try {
    if (-not (Test-Path (Join-Path $GatewayProjectPath "app.py"))) {
        throw "Không tìm thấy app.py tại '$GatewayProjectPath'. Dùng -GatewayProjectPath trỏ đến thư mục chứa app.py."
    }
    foreach ($port in @($RateLimitPort, $FailClosedPort)) {
        if (Test-TcpPortOpen -Port $port) { throw "Cổng $port đang được sử dụng. Đóng tiến trình đang dùng cổng đó hoặc chọn cổng khác rồi chạy lại." }
    }
    if (Test-TcpPortOpen -Port $UnavailableRedisPort) {
        throw "Cổng Redis mô phỏng lỗi $UnavailableRedisPort đang mở. Chọn một cổng localhost chưa sử dụng bằng -UnavailableRedisPort."
    }

    # Isolated rate-limit Gateway. Trust one X-Forwarded-For value ONLY in this temporary test process
    # so the test can use a unique synthetic IP and avoid colliding with an existing local counter.
    $rateEnv = @{
        REDIS_URL = $TestRedisUrl
        PORT = [string]$RateLimitPort
        MAX_REQUESTS = "3"
        TIME_WINDOW = "10"
        TRUSTED_X_FOR_COUNT = "1"
        TRUSTED_X_PROTO_COUNT = "0"
    }
    $rateProc = Start-TemporaryGateway -Name "rate-limit" -Port $RateLimitPort -Environment $rateEnv
    if (-not (Wait-ForPort -Port $RateLimitPort)) {
        Add-Result "Temporary rate-limit Gateway starts" $false "No listener on port $RateLimitPort. Check logs: $($rateProc.Stderr)"
        throw "Rate-limit Gateway did not start."
    }

    $health = Invoke-Probe -Url "http://127.0.0.1:$RateLimitPort/healthz" -Method GET
    $healthPass = $health.StatusCode -eq 200
    Add-Result "Temporary Gateway connects to isolated Redis DB" $healthPass ("HTTP {0}; body={1}" -f $health.StatusCode, $health.Body)
    if (-not $healthPass) { throw "Isolated Redis DB is not healthy; rate-limit checks stopped to avoid misleading results." }

    $lastOctet = Get-Random -Minimum 1 -Maximum 255
    $syntheticIp = "198.51.100.$lastOctet"
    $statuses = @()
    $fourth = $null
    for ($i = 1; $i -le 4; $i++) {
        $response = Invoke-Probe -Url "http://127.0.0.1:$RateLimitPort/api/chuyen-khoan" -Method POST -Headers @{
            "Origin" = "https://integration-test.invalid"
            "X-Forwarded-For" = $syntheticIp
            "Content-Type" = "application/json"
        } -Body "{}"
        $statuses += $response.StatusCode
        if ($i -eq 4) { $fourth = $response }
    }
    $firstThreePass = (($statuses[0] -eq 403) -and ($statuses[1] -eq 403) -and ($statuses[2] -eq 403))
    Add-Result "First three requests pass rate limit then are rejected by Origin guard" $firstThreePass ("HTTP statuses: {0}" -f ($statuses -join ", "))
    $fourthPass = ($statuses[3] -eq 429)
    Add-Result "Fourth request exceeds limit and returns 429" $fourthPass ("HTTP {0}; expected 429" -f $statuses[3])
    $retryAfter = ""
    if ($fourth -and $fourth.Headers) { $retryAfter = [string]$fourth.Headers["Retry-After"] }
    Add-Result "Rate-limited response includes Retry-After" (-not [string]::IsNullOrWhiteSpace($retryAfter)) ("Retry-After='{0}'" -f $retryAfter)

    # A separate process uses a known-unavailable local Redis port. It must fail closed.
    $failEnv = @{
        REDIS_URL = "redis://127.0.0.1:$UnavailableRedisPort/0"
        PORT = [string]$FailClosedPort
        MAX_REQUESTS = "5"
        TIME_WINDOW = "10"
        TRUSTED_X_FOR_COUNT = "0"
        TRUSTED_X_PROTO_COUNT = "0"
    }
    $failProc = Start-TemporaryGateway -Name "fail-closed" -Port $FailClosedPort -Environment $failEnv
    if (-not (Wait-ForPort -Port $FailClosedPort)) {
        Add-Result "Temporary fail-closed Gateway starts" $false "No listener on port $FailClosedPort. Check logs: $($failProc.Stderr)"
        throw "Fail-closed Gateway did not start."
    }

    $degradedHealth = Invoke-Probe -Url "http://127.0.0.1:$FailClosedPort/healthz" -Method GET
    Add-Result "Health check reports Redis outage as 503" ($degradedHealth.StatusCode -eq 503) ("HTTP {0}; expected 503; body={1}" -f $degradedHealth.StatusCode, $degradedHealth.Body)

    $blockedApi = Invoke-Probe -Url "http://127.0.0.1:$FailClosedPort/api/tai-khoan" -Method GET
    Add-Result "API request fails closed when Redis is unavailable" ($blockedApi.StatusCode -eq 503) ("HTTP {0}; expected 503; body={1}" -f $blockedApi.StatusCode, $blockedApi.Body)
}
catch {
    Write-Host ("ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
}
finally {
    Stop-TemporaryProcesses
}

Write-Host ""
$passedCount = @($script:Results | Where-Object { $_.Result -eq "PASS" }).Count
$failedCount = @($script:Results | Where-Object { $_.Result -eq "FAIL" }).Count
Write-Host ("Summary: {0} PASS; {1} FAIL; {2} total" -f $passedCount, $failedCount, $script:Results.Count) -ForegroundColor Cyan
Write-Host "Temporary Gateway processes have been stopped (if they started)."
Write-Host "Log directory: $script:LogDirectory"
if (Test-Path $script:LogDirectory) {
    $errorLogs = Get-ChildItem $script:LogDirectory -Filter "*.stderr.log" -ErrorAction SilentlyContinue
    foreach ($log in $errorLogs) {
        $logContent = Get-Content $log.FullName -ErrorAction SilentlyContinue | Select-Object -Last 8
        if ($logContent) {
            Write-Host "--- $($log.Name) (last 8 lines) ---" -ForegroundColor DarkGray
            $logContent | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
        }
    }
}
Write-Host ""
$script:Results | Format-Table -AutoSize
if ($failedCount -gt 0) { exit 1 }
if ($script:Results.Count -eq 0) { exit 2 }
exit 0
