param(
    [string]$GatewayBaseUrl = "http://127.0.0.1:8081",
    [string]$AllowedOrigin = "http://localhost:8080",
    [string]$ApiPath = "/api/tai-khoan"
)

# Finora Flask Gateway integration smoke tests.
# Safe by design: no Redis keys are deleted/created and no valid JWT is sent.
# Run against a local test environment, not a public/production endpoint.

$ErrorActionPreference = "Stop"
$script:Results = @()
$GatewayBaseUrl = $GatewayBaseUrl.TrimEnd('/')
$DisallowedOrigin = "https://integration-test.invalid"

function Invoke-Probe {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][ValidateSet("GET", "OPTIONS", "POST")][string]$Method,
        [hashtable]$Headers = @{},
        [string]$Body = $null
    )

    $request = [System.Net.HttpWebRequest]::Create($Url)
    $request.Method = $Method
    $request.Timeout = 7000
    $request.ReadWriteTimeout = 7000
    $request.AllowAutoRedirect = $false
    $request.KeepAlive = $false

    foreach ($key in $Headers.Keys) {
        if ($key -ieq "Content-Type") {
            $request.ContentType = [string]$Headers[$key]
        }
        else {
            $request.Headers[$key] = [string]$Headers[$key]
        }
    }

    # A typed [string] parameter may coerce $null to an empty string in Windows PowerShell.
    # Check whether -Body was explicitly supplied so GET/OPTIONS never call GetRequestStream().
    if ($PSBoundParameters.ContainsKey("Body")) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
        $request.ContentLength = $bytes.Length
        if (-not $request.ContentType) {
            $request.ContentType = "application/json"
        }
        $stream = $request.GetRequestStream()
        try { $stream.Write($bytes, 0, $bytes.Length) }
        finally { $stream.Dispose() }
    }

    $response = $null
    try {
        $response = $request.GetResponse()
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $response = $_.Exception.Response
        }
        else {
            return [pscustomobject]@{
                StatusCode = 0
                Headers = $null
                Body = $_.Exception.Message
            }
        }
    }

    try {
        $reader = New-Object -TypeName System.IO.StreamReader -ArgumentList $response.GetResponseStream()
        try { $responseBody = $reader.ReadToEnd() }
        finally { $reader.Dispose() }

        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Headers = $response.Headers
            Body = $responseBody
        }
    }
    finally {
        if ($response) { $response.Dispose() }
    }
}

function Get-HeaderValue {
    param($Response, [string]$Name)
    if ($null -eq $Response -or $null -eq $Response.Headers) { return "" }
    $value = $Response.Headers[$Name]
    if ($null -eq $value) { return "" }
    return [string]$value
}

function Add-Result {
    param([string]$Name, [bool]$Passed, [string]$Detail)
    $label = if ($Passed) { "PASS" } else { "FAIL" }
    $color = if ($Passed) { "Green" } else { "Red" }
    $script:Results += [pscustomobject]@{
        Test = $Name
        Result = $label
        Detail = $Detail
    }
    Write-Host ("[{0}] {1} - {2}" -f $label, $Name, $Detail) -ForegroundColor $color
}

Write-Host "Finora Gateway integration regression" -ForegroundColor Cyan
Write-Host "Gateway: $GatewayBaseUrl"
Write-Host "Allowed Origin: $AllowedOrigin"
Write-Host "Lưu ý: script không gửi JWT, không sửa Redis và không tạo giao dịch."
Write-Host ""

# 1. Health check and real Redis dependency.
$health = Invoke-Probe -Url "$GatewayBaseUrl/healthz" -Method GET
$healthJson = $null
if ($health.StatusCode -eq 200) {
    try { $healthJson = $health.Body | ConvertFrom-Json } catch { $healthJson = $null }
}
$healthPass = ($health.StatusCode -eq 200 -and $null -ne $healthJson -and
    [string]$healthJson.status -eq "ok" -and [string]$healthJson.redis -eq "connected")
Add-Result "Health check confirms Redis connected" $healthPass ("HTTP {0}; body={1}" -f $health.StatusCode, $health.Body)

# 2. Allowed CORS preflight.
$allowedPreflight = Invoke-Probe -Url "$GatewayBaseUrl$ApiPath" -Method OPTIONS -Headers @{
    "Origin" = $AllowedOrigin
    "Access-Control-Request-Method" = "GET"
    "Access-Control-Request-Headers" = "authorization"
}
$allowedOriginHeader = Get-HeaderValue $allowedPreflight "Access-Control-Allow-Origin"
$allowedMethods = Get-HeaderValue $allowedPreflight "Access-Control-Allow-Methods"
$allowedHeaders = Get-HeaderValue $allowedPreflight "Access-Control-Allow-Headers"
$preflightPass = ($allowedPreflight.StatusCode -eq 204 -and
    $allowedOriginHeader -eq $AllowedOrigin -and
    $allowedMethods -match '(?i)(^|,\s*)GET(\s*,|$)' -and
    $allowedHeaders -match '(?i)(^|,\s*)authorization(\s*,|$)')
Add-Result "Allowed Origin preflight grants requested CORS access" $preflightPass ("HTTP {0}; ACAO='{1}'; methods='{2}'; headers='{3}'" -f $allowedPreflight.StatusCode, $allowedOriginHeader, $allowedMethods, $allowedHeaders)

# 3. Disallowed CORS preflight must not grant browser access.
$deniedPreflight = Invoke-Probe -Url "$GatewayBaseUrl$ApiPath" -Method OPTIONS -Headers @{
    "Origin" = $DisallowedOrigin
    "Access-Control-Request-Method" = "GET"
    "Access-Control-Request-Headers" = "authorization"
}
$deniedOriginHeader = Get-HeaderValue $deniedPreflight "Access-Control-Allow-Origin"
$deniedPreflightPass = ($deniedPreflight.StatusCode -eq 204 -and [string]::IsNullOrWhiteSpace($deniedOriginHeader))
Add-Result "Disallowed Origin preflight grants no CORS permission" $deniedPreflightPass ("HTTP {0}; ACAO='{1}'" -f $deniedPreflight.StatusCode, $deniedOriginHeader)

# 4. GET from a disallowed Origin should still reach backend authentication,
# but must not receive Access-Control-Allow-Origin for that disallowed site.
$badOriginGet = Invoke-Probe -Url "$GatewayBaseUrl$ApiPath" -Method GET -Headers @{
    "Origin" = $DisallowedOrigin
}
$badGetAco = Get-HeaderValue $badOriginGet "Access-Control-Allow-Origin"
$badGetPass = ($badOriginGet.StatusCode -eq 401 -and [string]::IsNullOrWhiteSpace($badGetAco))
Add-Result "GET with disallowed Origin reaches backend auth without CORS grant" $badGetPass ("HTTP {0}; ACAO='{1}' (expected HTTP 401 without JWT)" -f $badOriginGet.StatusCode, $badGetAco)

# 5. A state-changing request with a disallowed Origin must be stopped by Gateway.
# No valid JWT is sent; even if the Origin guard were broken, the backend should not
# authorize this request. The empty-object payload is not a valid transfer command.
$badOriginPost = Invoke-Probe -Url "$GatewayBaseUrl/api/chuyen-khoan" -Method POST -Headers @{
    "Origin" = $DisallowedOrigin
    "Content-Type" = "application/json"
} -Body "{}"
$nosniff = Get-HeaderValue $badOriginPost "X-Content-Type-Options"
$badPostPass = ($badOriginPost.StatusCode -eq 403)
Add-Result "State-changing request with disallowed Origin is blocked" $badPostPass ("HTTP {0}; expected 403" -f $badOriginPost.StatusCode)
Add-Result "Security header exists on rejection response" ($nosniff -eq "nosniff") ("X-Content-Type-Options='{0}'" -f $nosniff)

Write-Host ""
$passedCount = @($script:Results | Where-Object { $_.Result -eq "PASS" }).Count
$failedCount = @($script:Results | Where-Object { $_.Result -eq "FAIL" }).Count
Write-Host ("Summary: {0} PASS; {1} FAIL; {2} total" -f $passedCount, $failedCount, $script:Results.Count) -ForegroundColor Cyan
Write-Host ""
$script:Results | Format-Table -AutoSize

if ($failedCount -gt 0) {
    exit 1
}
exit 0
