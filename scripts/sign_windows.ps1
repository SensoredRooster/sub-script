# Signs files with Azure Artifact Signing (signtool + Azure.CodeSigning.Dlib) and verifies them.
# Auth: DefaultAzureCredential, e.g. `az login` as an account with the Artifact Signing
# Certificate Profile Signer role. Overrides: -SignToolPath/-DlibPath/-MetadataPath or
# SUBSCRIPT_SIGNTOOL / SUBSCRIPT_SIGN_DLIB.
param(
 [Parameter(Mandatory)][string[]]$Files,
 [string]$SignToolPath = $env:SUBSCRIPT_SIGNTOOL,
 [string]$DlibPath = $env:SUBSCRIPT_SIGN_DLIB,
 [string]$MetadataPath
)
$ErrorActionPreference = 'Stop'
if (-not $MetadataPath) { $MetadataPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'signing\metadata.json' }
if (-not $SignToolPath) {
 $c = @(Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
 if (-not $c) { throw 'signtool.exe (x64, Windows SDK 10.0.22621+) not found. Install Microsoft.Azure.ArtifactSigningClientTools or pass -SignToolPath.' }
 $SignToolPath = $c[0].FullName
}
if (-not $DlibPath) {
 $roots = @("$env:LOCALAPPDATA\Microsoft\MicrosoftArtifactSigningClientTools", "$env:LOCALAPPDATA\Microsoft\MicrosoftTrustedSigningClientTools", "$env:USERPROFILE\.nuget\packages\microsoft.artifactsigning.client", "$env:USERPROFILE\.nuget\packages\microsoft.trusted.signing.client")
 $c = @(Get-ChildItem $roots -Recurse -Filter Azure.CodeSigning.Dlib.dll -ErrorAction SilentlyContinue | Sort-Object { $_.FullName -notmatch 'x64' })
 if (-not $c) { throw 'Azure.CodeSigning.Dlib.dll not found. Install Microsoft.Azure.ArtifactSigningClientTools or pass -DlibPath.' }
 $DlibPath = $c[0].FullName
}
if (-not (Test-Path $MetadataPath)) { throw "Signing metadata not found: $MetadataPath" }
& $SignToolPath sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 /dlib $DlibPath /dmdf $MetadataPath @Files
if ($LASTEXITCODE -ne 0) { throw 'Code signing failed. Run az login with an account holding the Artifact Signing Certificate Profile Signer role.' }
& $SignToolPath verify /pa /v @Files
if ($LASTEXITCODE -ne 0) { throw 'Signature verification failed.' }
