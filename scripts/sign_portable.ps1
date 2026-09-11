# Sign portable AI-Agent-Studio EXE(s) with Authenticode (Windows) or note osslsigncode.
# Pipeline only — certificate is USER-PROVIDED. Self-signed is for DEV ONLY (not distribution trust).
#
# Usage:
#   .\scripts\sign_portable.ps1                          # sign dist\AI-Agent-Studio\*.exe
#   .\scripts\sign_portable.ps1 -Path .\dist\...\foo.exe
#   .\scripts\sign_portable.ps1 -CertPath $env:AAS_SIGN_CERT -Password $env:AAS_SIGN_PASSWORD
#   .\scripts\sign_portable.ps1 -DryRun                  # resolve targets / show plan, no sign
#   .\scripts\sign_portable.ps1 -Help
#
# Env (preferred for CI / secrets):
#   AAS_SIGN_CERT       Path to .pfx / .p12 (or cert thumbprint if -UseStore)
#   AAS_SIGN_PASSWORD   PFX password (optional empty for unprotected PFX)
#   AAS_SIGN_TIMESTAMP  Timestamp URL (default DigiCert)
#   AAS_SIGN_SKIP=1     Force skip (exit 0)
#
# Exit codes: 0 = signed or gracefully skipped; 1 = hard failure after attempting sign.

[CmdletBinding()]
param(
    [string]$Path = "",
    [string]$CertPath = "",
    [string]$Password = "",
    [string]$TimestampUrl = "",
    [switch]$UseStore,
    [switch]$SelfSignedDev,
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Show-Help {
    @"
sign_portable.ps1 — Authenticode sign portable AI-Agent-Studio EXE(s)

  -Path <file|dir>     EXE or folder (default: dist\AI-Agent-Studio\*.exe under repo root)
  -CertPath <pfx>      Certificate PFX/P12 (or set AAS_SIGN_CERT)
  -Password <str>      PFX password (or AAS_SIGN_PASSWORD)
  -TimestampUrl <url>  RFC3161 timestamp (or AAS_SIGN_TIMESTAMP)
  -UseStore            Treat -CertPath / AAS_SIGN_CERT as thumbprint in Cert:\CurrentUser\My
  -SelfSignedDev       Allow self-signed / untrusted cert (DEV ONLY — NOT for distribution)
  -DryRun              Print plan; do not sign
  -Help                This text

Skips gracefully (exit 0) when cert/tools missing, unless a sign was requested and failed mid-flight.
See docs/CODE_SIGNING.md
"@
}

if ($Help) {
    Show-Help
    exit 0
}

if ($env:AAS_SIGN_SKIP -eq "1") {
    Write-Host "sign_portable: AAS_SIGN_SKIP=1 — skipping."
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = $PSScriptRoot }

if (-not $CertPath) { $CertPath = $env:AAS_SIGN_CERT }
if (-not $Password -and $env:AAS_SIGN_PASSWORD) { $Password = $env:AAS_SIGN_PASSWORD }
if (-not $TimestampUrl) {
    if ($env:AAS_SIGN_TIMESTAMP) { $TimestampUrl = $env:AAS_SIGN_TIMESTAMP }
    else { $TimestampUrl = "http://timestamp.digicert.com" }
}

# Resolve target EXEs
$targets = @()
if ($Path) {
    $p = $Path
    if (-not [System.IO.Path]::IsPathRooted($p)) {
        $p = Join-Path $RepoRoot $p
    }
    if (Test-Path -LiteralPath $p -PathType Container) {
        $targets = @(Get-ChildItem -LiteralPath $p -Filter *.exe -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    } elseif (Test-Path -LiteralPath $p -PathType Leaf) {
        $targets = @($p)
    } else {
        Write-Host "sign_portable: path not found: $Path — skipping."
        exit 0
    }
} else {
    $defaultDir = Join-Path $RepoRoot "dist\AI-Agent-Studio"
    if (Test-Path -LiteralPath $defaultDir) {
        $targets = @(Get-ChildItem -LiteralPath $defaultDir -Filter *.exe -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
}

if (-not $targets -or $targets.Count -eq 0) {
    Write-Host "sign_portable: no EXE targets under dist\AI-Agent-Studio (or -Path) — skipping."
    exit 0
}

Write-Host "sign_portable: targets ($($targets.Count)):"
foreach ($t in $targets) { Write-Host "  - $t" }

if ($DryRun) {
    Write-Host "sign_portable: DryRun — would sign with cert='$CertPath' timestamp='$TimestampUrl' SelfSignedDev=$SelfSignedDev"
    if (-not $CertPath) {
        Write-Host "sign_portable: DryRun note — no cert set (AAS_SIGN_CERT / -CertPath); live run would skip."
    }
    exit 0
}

if (-not $CertPath) {
    Write-Host "sign_portable: no AAS_SIGN_CERT / -CertPath — skipping (unsigned build is OK for local use)."
    Write-Host "  See docs/CODE_SIGNING.md to sign for distribution."
    exit 0
}

# Load certificate
$cert = $null
try {
    if ($UseStore) {
        $thumb = ($CertPath -replace '\s', '').ToUpperInvariant()
        $cert = Get-ChildItem Cert:\CurrentUser\My -ErrorAction Stop | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
        if (-not $cert) {
            $cert = Get-ChildItem Cert:\LocalMachine\My -ErrorAction SilentlyContinue | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
        }
        if (-not $cert) {
            Write-Host "sign_portable: thumbprint not found in store: $CertPath — skipping."
            exit 0
        }
    } else {
        if (-not (Test-Path -LiteralPath $CertPath)) {
            Write-Host "sign_portable: cert file not found: $CertPath — skipping."
            exit 0
        }
        $secure = $null
        if ($Password) {
            $secure = ConvertTo-SecureString -String $Password -AsPlainText -Force
        }
        if ($secure) {
            $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath, $secure)
        } else {
            $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertPath, "")
        }
    }
} catch {
    Write-Host "sign_portable: failed to load cert ($($_.Exception.Message)) — skipping."
    exit 0
}

if (-not $cert.HasPrivateKey) {
    Write-Host "sign_portable: certificate has no private key — skipping."
    exit 0
}

# Self-signed / untrusted guard
$chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
$chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
$trusted = $chain.Build($cert)
if (-not $trusted -and -not $SelfSignedDev) {
    Write-Host "sign_portable: cert chain not trusted. Pass -SelfSignedDev for DEV ONLY (NOT for distribution trust), or use a real Authenticode cert."
    Write-Host "  See docs/CODE_SIGNING.md"
    exit 0
}
if (-not $trusted -and $SelfSignedDev) {
    Write-Warning "SELF-SIGNED / UNTRUSTED cert — DEV ONLY. Do NOT distribute as trusted. Windows SmartScreen will still warn."
}

if (-not (Get-Command Set-AuthenticodeSignature -ErrorAction SilentlyContinue)) {
    Write-Host "sign_portable: Set-AuthenticodeSignature unavailable — skipping."
    exit 0
}

$failed = 0
foreach ($exe in $targets) {
    try {
        Write-Host "sign_portable: signing $exe ..."
        $result = Set-AuthenticodeSignature -FilePath $exe -Certificate $cert -TimestampServer $TimestampUrl -HashAlgorithm SHA256
        $status = $result.Status
        Write-Host "  Status: $status"
        if ($status -ne "Valid" -and $status -ne "UnknownError") {
            # UnknownError sometimes with self-signed + timestamp; still check signature present
            $check = Get-AuthenticodeSignature -FilePath $exe
            if ($check.Status -eq "NotSigned") {
                Write-Host "  ERROR: still NotSigned"
                $failed++
            } elseif ($SelfSignedDev) {
                Write-Host "  SelfSignedDev: accepting status $($check.Status)"
            } elseif ($check.Status -ne "Valid") {
                Write-Host "  WARN: signature status $($check.Status) (may need trusted CA)"
                $failed++
            }
        }
    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)"
        $failed++
    }
}

if ($failed -gt 0) {
    Write-Host "sign_portable: $failed file(s) failed to sign."
    exit 1
}

Write-Host "sign_portable: done. Verify with: Get-AuthenticodeSignature -FilePath <exe>"
exit 0
