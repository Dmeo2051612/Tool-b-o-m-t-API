$ErrorActionPreference = 'Stop'

function Get-GitOutput {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $output = & git @Arguments 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Git command failed: git $($Arguments -join ' ')`n$($output -join "`n")"
    }
    return ,@($output | ForEach-Object { [string]$_ })
}

function Test-TextBytes {
    param([byte[]]$Bytes)
    if ($null -eq $Bytes -or $Bytes.Length -eq 0) { return $true }
    $limit = [Math]::Min($Bytes.Length, 4096)
    for ($i = 0; $i -lt $limit; $i++) {
        if ($Bytes[$i] -eq 0) { return $false }
    }
    return $true
}

function Find-SensitiveLines {
    param(
        [string]$Path,
        [string[]]$Lines,
        [string]$Source
    )

    $findings = @()
    $secretAssignment = '(?i)\b(password|passwd|pwd|client[_-]?secret|api[_-]?key|access[_-]?token|refresh[_-]?token|secret)\b\s*["'']?\s*[:=]\s*["'']?([^"''\s,;]+)'
    $placeholders = '(?i)^(your[_-]?(password|secret|api[_-]?key|token)|change[_-]?me|replace[_-]?me|<[^>]+>|\$\{[^}]+\}|%[^%]+%|null|none|example|redacted)$'

    for ($i = 0; $i -lt $Lines.Count; $i++) {
        $line = [string]$Lines[$i]
        $lineNumber = $i + 1
        $reasons = New-Object System.Collections.Generic.List[string]

        if ($line -match '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----') {
            $reasons.Add('private-key material')
        }
        if ($line -match '(?i)\bAKIA[0-9A-Z]{16}\b') {
            $reasons.Add('AWS access-key pattern')
        }
        if ($line -match '\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{10,}\b') {
            $reasons.Add('JWT-like token')
        }
        if ($line -match '(?i)\bsk-[A-Za-z0-9_-]{20,}\b') {
            $reasons.Add('API-key-like token')
        }

        $match = [regex]::Match($line, $secretAssignment)
        if ($match.Success) {
            $value = $match.Groups[2].Value.Trim().TrimEnd(')', '}', ']')
            $isPlaceholder = ($value -match $placeholders)
            $isCodeReference = ($value -match '(?i)^(request|model|dto|config|configuration|environment|options|settings|builder|_configuration)\.' -or
                                $value -match '(?i)^Environment\.GetEnvironmentVariable' -or
                                $value -match '^\$env:')
            if (-not $isPlaceholder -and -not $isCodeReference) {
                $reasons.Add("possible hard-coded $($match.Groups[1].Value)")
            }
        }

        if ($reasons.Count -gt 0) {
            $findings += [pscustomobject]@{
                Path = $Path
                Line = $lineNumber
                Source = $Source
                Reason = ($reasons -join ', ')
            }
        }
    }
    return $findings
}

try {
    $rootOutput = Get-GitOutput -Arguments @('rev-parse', '--show-toplevel')
    $repoRoot = ([string]$rootOutput[0]).Trim()
    if (-not $repoRoot) { throw 'Could not determine repository root.' }
    Set-Location $repoRoot

    Write-Host ''
    Write-Host 'Finora pre-commit audit' -ForegroundColor Cyan
    Write-Host "Repository: $repoRoot"
    Write-Host 'This script does not commit, stage, edit, or upload files.'

    $status = Get-GitOutput -Arguments @('status', '--short')
    Write-Host "`n--- Git status ---" -ForegroundColor Cyan
    if ($status.Count -eq 0 -or ($status.Count -eq 1 -and [string]::IsNullOrWhiteSpace($status[0]))) {
        Write-Host '[INFO] Working tree is clean.' -ForegroundColor Yellow
    } else {
        $status | ForEach-Object { Write-Host $_ }
    }

    $staged = @(Get-GitOutput -Arguments @('diff', '--cached', '--name-only', '--diff-filter=ACMR')) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $unstaged = @(Get-GitOutput -Arguments @('diff', '--name-only', '--diff-filter=ACMR')) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $untracked = @(Get-GitOutput -Arguments @('ls-files', '--others', '--exclude-standard')) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }

    Write-Host "`nStaged files: $($staged.Count) | Unstaged tracked files: $($unstaged.Count) | Untracked non-ignored files: $($untracked.Count)"
    if ($staged.Count -gt 0) {
        Write-Host "`n--- Staged paths (these are what a normal commit includes) ---" -ForegroundColor Cyan
        $staged | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host '[INFO] No staged changes. There is currently nothing prepared for a normal commit.' -ForegroundColor Yellow
    }

    Write-Host "`n--- Whitespace/error check ---" -ForegroundColor Cyan
    $checkFailed = $false
    $cachedCheck = & git diff --cached --check 2>&1
    if ($LASTEXITCODE -ne 0 -or $cachedCheck.Count -gt 0) {
        $checkFailed = $true
        Write-Host '[WARN] Staged diff check found issues:' -ForegroundColor Yellow
        $cachedCheck | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host '[PASS] git diff --cached --check'
    }
    $workCheck = & git diff --check 2>&1
    if ($LASTEXITCODE -ne 0 -or $workCheck.Count -gt 0) {
        $checkFailed = $true
        Write-Host '[WARN] Unstaged diff check found issues:' -ForegroundColor Yellow
        $workCheck | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host '[PASS] git diff --check'
    }

    $findings = @()
    $sensitiveFilePatterns = @(
        '(^|/)\.env($|\.)',
        '(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)$',
        '\.(pem|pfx|p12|key)$',
        '(^|/)finora_.*_state\.json$',
        '(^|/)finora_idempotency_test_state\.json$'
    )

    $pathsToInspect = @($staged + $unstaged + $untracked | Sort-Object -Unique)
    foreach ($path in $pathsToInspect) {
        $normalized = $path -replace '\\', '/'
        foreach ($pattern in $sensitiveFilePatterns) {
            if ($normalized -match $pattern) {
                $findings += [pscustomobject]@{
                    Path = $path
                    Line = 0
                    Source = 'filename'
                    Reason = 'sensitive/configuration/private-key/test-state filename; verify it is intentionally excluded from commit'
                }
                break
            }
        }

        $fullPath = Join-Path $repoRoot $path
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            try {
                $bytes = [System.IO.File]::ReadAllBytes($fullPath)
                if (Test-TextBytes -Bytes $bytes) {
                    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
                    $lines = @($text -split "`r?`n")
                    $findings += @(Find-SensitiveLines -Path $path -Lines $lines -Source 'working tree')
                }
            } catch {
                Write-Host "[WARN] Could not scan working-tree file: $path" -ForegroundColor Yellow
            }
        }
    }

    # Inspect the staged/index version as well, because it can differ from the working tree.
    foreach ($path in $staged) {
        $indexContent = & git show ":$path" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $indexLines = @($indexContent | ForEach-Object { [string]$_ })
            $findings += @(Find-SensitiveLines -Path $path -Lines $indexLines -Source 'staged/index version')
        }
    }

    Write-Host "`n--- Secret and state-file scan ---" -ForegroundColor Cyan
    if ($findings.Count -eq 0) {
        Write-Host '[PASS] No suspicious hard-coded secret patterns found in changed/untracked paths.' -ForegroundColor Green
        Write-Host '[INFO] Pattern scans cannot guarantee that all secrets are absent; manually review config files and staged diff.'
    } else {
        Write-Host "[WARN] Found $($findings.Count) item(s) to review. Secret values are deliberately not printed." -ForegroundColor Yellow
        $findings | Sort-Object Path, Line, Source, Reason -Unique | ForEach-Object {
            if ($_.Line -gt 0) {
                Write-Host ('[REVIEW] {0}:{1} ({2}) - {3}' -f $_.Path, $_.Line, $_.Source, $_.Reason) -ForegroundColor Yellow
            } else {
                Write-Host ('[REVIEW] {0} - {1}' -f $_.Path, $_.Reason) -ForegroundColor Yellow
            }
        }
    }

    Write-Host "`n--- Before committing ---" -ForegroundColor Cyan
    Write-Host '1. Confirm staged files are exactly the intended changes.'
    Write-Host '2. Do not add .env files, credentials, tokens, private keys, or test state JSON.'
    Write-Host '3. Review staged diff locally: git diff --cached'
    Write-Host '4. If no files are staged, do not create a commit yet.'

    if ($checkFailed -or $findings.Count -gt 0) {
        Write-Host "`nAudit finished with items to review; this is not an automatic pass." -ForegroundColor Yellow
    } else {
        Write-Host "`nAudit finished. Review staged content manually before committing." -ForegroundColor Green
    }
} catch {
    Write-Error $_
    exit 1
}
