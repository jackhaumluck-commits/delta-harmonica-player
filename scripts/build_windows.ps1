$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "单元测试失败，已停止打包"
    }

    python -m PyInstaller --clean --noconfirm DeltaHarmonicaPlayer.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 打包失败，退出码：$LASTEXITCODE"
    }

    $executable = Join-Path $projectRoot "dist\DeltaHarmonicaPlayer.exe"
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "打包完成，但没有找到 $executable"
    }

    $hash = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksum = "$executable.sha256"
    "$hash  DeltaHarmonicaPlayer.exe" | Set-Content -LiteralPath $checksum -Encoding ascii
    Write-Host "Windows 可执行文件：$executable"
    Write-Host "校验文件：$checksum"
    Write-Host "SHA256：$hash"
}
finally {
    Pop-Location
}
