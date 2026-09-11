# Code signing (portable EXE)

**Pipeline ready; certificate is user-provided.**  
This repo does **not** ship a purchasing/issuance flow for Authenticode certificates. Use the scripts below once **you** have a `.pfx` / `.p12` (or a cert in the Windows store).

| Script | Platform | Backend |
|--------|----------|---------|
| `scripts/sign_portable.ps1` | Windows (preferred) | `Set-AuthenticodeSignature` |
| `scripts/sign_portable.sh` | Linux/macOS/CI with wine-less PE signing | [`osslsigncode`](https://github.com/mtrojnar/osslsigncode) |

Both skip **gracefully** (exit 0) when the cert, tools, or EXE targets are missing — so unsigned local/dev builds stay frictionless.

---

## Quick start (after `build_portable.ps1`)

```powershell
# Optional: set secrets (do not commit)
$env:AAS_SIGN_CERT     = "C:\secrets\aas-codesign.pfx"
$env:AAS_SIGN_PASSWORD = "••••••••"   # omit if PFX has no password

# Sign default targets: dist\AI-Agent-Studio\*.exe
.\scripts\sign_portable.ps1

# Or explicit path
.\scripts\sign_portable.ps1 -Path .\dist\AI-Agent-Studio\AI-Agent-Studio.exe
```

`build_portable.ps1` invokes the sign script automatically after a successful PyInstaller build (still skips if no cert).

Cross-platform / CI:

```bash
export AAS_SIGN_CERT=/secure/aas-codesign.pfx
export AAS_SIGN_PASSWORD='••••••••'
./scripts/sign_portable.sh
# or: ./scripts/sign_portable.sh dist/AI-Agent-Studio/AI-Agent-Studio.exe
```

Dry-run / help (no cert required):

```powershell
.\scripts\sign_portable.ps1 -Help
.\scripts\sign_portable.ps1 -DryRun
```

```bash
./scripts/sign_portable.sh --help
./scripts/sign_portable.sh --dry-run
```

Force skip: `AAS_SIGN_SKIP=1`.

---

## Environment / parameters

| Name | Meaning |
|------|---------|
| `AAS_SIGN_CERT` / `-CertPath` / `--cert` | Path to PKCS#12 (`.pfx`/`.p12`). On PS with `-UseStore`, treat as thumbprint in `Cert:\CurrentUser\My`. |
| `AAS_SIGN_PASSWORD` / `-Password` / `--password` | PFX password (optional). |
| `AAS_SIGN_TIMESTAMP` / `-TimestampUrl` / `--timestamp` | Timestamp server (default `http://timestamp.digicert.com`). |
| `AAS_SIGN_SKIP=1` | Do nothing, exit 0. |
| `-SelfSignedDev` / `AAS_SIGN_SELF_SIGNED_DEV=1` / `--self-signed-dev` | **DEV ONLY** — see warning below. |

---

## How to obtain a real Authenticode certificate

1. **Buy / issue** an Authenticode (OV or EV) code-signing certificate from a public CA (DigiCert, Sectigo, SSL.com, GlobalSign, etc.). EV often requires a hardware token / HSM.
2. Export or receive a **PKCS#12** (`.pfx`) that includes the **private key**, or import into the Windows certificate store and use the thumbprint with `-UseStore`.
3. Store the PFX and password in a **secret store** (CI secrets, password manager, HSM). **Never commit** certs or passwords to git.
4. Set `AAS_SIGN_CERT` + `AAS_SIGN_PASSWORD` (or pass parameters) and run the sign script after each portable build.
5. Prefer a **timestamp server** so the signature remains verifiable after the cert expires.

Organization / EV policies, identity verification, and token PIN workflows are **outside** this repo — follow your CA’s docs.

---

## Verify signatures

### Windows PowerShell

```powershell
Get-AuthenticodeSignature -FilePath .\dist\AI-Agent-Studio\AI-Agent-Studio.exe |
  Format-List Status, StatusMessage, SignerCertificate, TimeStamperCertificate
```

Expect `Status : Valid` for a trusted CA-signed + timestamped binary. Explorer → file Properties → Digital Signatures should list your publisher.

### osslsigncode

```bash
osslsigncode verify -in dist/AI-Agent-Studio/AI-Agent-Studio.exe
```

---

## Self-signed / development path (NOT for distribution trust)

You may generate a **self-signed** cert to practice the pipeline locally:

```powershell
# DEV ONLY — Windows example
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=AI-Agent-Studio-DEV" `
  -CertStoreLocation Cert:\CurrentUser\My
$password = ConvertTo-SecureString -String "dev-only" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath .\aas-dev-codesign.pfx -Password $password
```

Then:

```powershell
$env:AAS_SIGN_CERT = ".\aas-dev-codesign.pfx"
$env:AAS_SIGN_PASSWORD = "dev-only"
.\scripts\sign_portable.ps1 -SelfSignedDev
```

### Warning

- Self-signed signatures **do not** establish publisher trust for end users.
- Windows SmartScreen / Defender will still warn or block unknown publishers.
- **Do not** ship self-signed builds as “signed and trusted.”
- Use `-SelfSignedDev` / `--self-signed-dev` only on machines you control for pipeline testing.

---

## Build hook

After PyInstaller succeeds, `build_portable.ps1` runs:

```powershell
& (Join-Path $PSScriptRoot "scripts\sign_portable.ps1")
```

If secrets are unset, signing is skipped and the unsigned EXE remains usable locally. Documented also in [LAUNCH.md](LAUNCH.md).

---

## Related

- Portable build: `build_portable.ps1` · [LAUNCH.md](LAUNCH.md)
- Release docs gate: [RELEASE.md](RELEASE.md)
- Roadmap note: pipeline ready; cert is user-provided (1.28.1)
