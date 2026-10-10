<#
  cad_open.ps1 - open a DXF/DWG in the desktop AutoCAD (Windows).

  AutoCAD is auto-detected under "C:\Program Files\Autodesk\AutoCAD *\acad.exe".
  Override with -AcadExe "D:\...\acad.exe" or the ACAD_EXE environment variable.

  Usage:
      powershell -ExecutionPolicy Bypass -File cad_open.ps1 -Path ".\out.dxf"
#>
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$AcadExe
)

if (-not $AcadExe -and $env:ACAD_EXE) { $AcadExe = $env:ACAD_EXE }
if (-not $AcadExe) {
    $cands = @()
    $cands += Get-ChildItem 'C:\Program Files\Autodesk' -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'AutoCAD*' } |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'acad.exe' }
    $AcadExe = $cands | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $AcadExe -or -not (Test-Path -LiteralPath $AcadExe)) {
    throw "AutoCAD not found. Pass -AcadExe <path to acad.exe> or set the ACAD_EXE environment variable."
}

$full = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
Start-Process -FilePath $AcadExe -ArgumentList @($full)
Write-Output ("opened in AutoCAD: " + $full)
