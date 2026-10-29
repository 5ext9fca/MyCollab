param(
    [string]$AppPath = 'C:\Program Files\MyCollab\MyCollab.exe',
    [switch]$SmokeOnly,
    [string]$ReportRoot = (Join-Path $PSScriptRoot '..\..\test-results\local-windows'),
    [string]$LiveServer = ''
)
$ErrorActionPreference = 'Stop'
if ($SmokeOnly -and $LiveServer) { throw 'SmokeOnly 与真实站点 LiveServer 模式不能同时使用。' }
if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) { throw '本入口仅用于本地 Windows。' }
$shared = Join-Path $PSScriptRoot '..\shared'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
if (-not (Test-Path -LiteralPath $AppPath -PathType Leaf)) { throw '找不到指定的 MyCollab.exe。' }
$node = (Get-Command node.exe -ErrorAction Stop).Source
$npm = Join-Path (Split-Path $node) 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path -LiteralPath $npm)) { throw '需要包含 npm 的 Windows Node 安装。' }

# 将套件复制到本机临时目录，支持从 WSL UNC 路径启动，避免 cmd 的 UNC 工作目录限制。
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ('mycollab-windows-e2e-' + $runId)
$report = Join-Path $ReportRoot $runId
function Get-Sha256([string]$FilePath) {
    $stream = [System.IO.File]::OpenRead($FilePath)
    $hash = [System.Security.Cryptography.SHA256]::Create()
    try { return ([System.BitConverter]::ToString($hash.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $hash.Dispose() }
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null
foreach ($name in @('package.json', 'package-lock.json', 'playwright.config.mjs', 'server.mjs', 'server.test.mjs', 'fixtures.mjs', 'acceptance.spec.mjs', 'live.config.mjs', 'live.spec.mjs')) {
    Copy-Item -LiteralPath (Join-Path $shared $name) -Destination $stage
}
$oldBinary = $env:MYCOLLAB_TEST_APP_BINARY
$oldPlatform = $env:MYCOLLAB_TEST_PLATFORM
$oldServer = $env:MYCOLLAB_ACCEPTANCE_SERVER
$oldRunAsNode = $env:ELECTRON_RUN_AS_NODE
$result = 1
Push-Location $stage
try {
    $env:MYCOLLAB_TEST_PLATFORM = 'win32'
    $env:MYCOLLAB_ACCEPTANCE_SERVER = $LiveServer
    $env:MYCOLLAB_TEST_APP_BINARY = (Resolve-Path -LiteralPath $AppPath).Path
    Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
    & $node $npm ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw '测试依赖安装失败。' }
    & $node --test server.test.mjs
    if ($LASTEXITCODE -ne 0) { throw '本机测试服务自检失败。' }
    $testArgs = @('node_modules\@playwright\test\cli.js', 'test')
    if ($LiveServer) { $testArgs += @('--config', 'live.config.mjs') }
    if ($SmokeOnly) { $testArgs += @('--grep-invert', '@known-issue') }
    & $node @testArgs
    $result = $LASTEXITCODE
} finally {
    Pop-Location
    $env:MYCOLLAB_TEST_APP_BINARY = $oldBinary
    $env:MYCOLLAB_TEST_PLATFORM = $oldPlatform
    $env:MYCOLLAB_ACCEPTANCE_SERVER = $oldServer
    $env:ELECTRON_RUN_AS_NODE = $oldRunAsNode
    New-Item -ItemType Directory -Path $report -Force | Out-Null
    if (Test-Path -LiteralPath (Join-Path $stage 'results')) {
        Copy-Item -Path (Join-Path $stage 'results\*') -Destination $report -Recurse
    }
    $metadata = [ordered]@{
        app = $AppPath
        exeSha256 = Get-Sha256 $AppPath
        appAsarSha256 = Get-Sha256 (Join-Path (Split-Path $AppPath) 'resources\app.asar')
        node = (& $node --version)
        os = [System.Environment]::OSVersion.VersionString
        smokeOnly = [bool]$SmokeOnly
        liveServerMode = [bool]$LiveServer
        exitCode = $result
        scope = $(if ($LiveServer) { 'Windows 安装版与指定 HTTPS 站点；用户手动登录；无模型调用、trace 或截图。' } else { 'Windows 安装版 Electron + 本机 HTTP 夹具；非 Django、真实供应商、双机网络或原生对话框验收。' })
    }
    $metadata | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $report 'run.json') -Encoding UTF8
    Write-Host ('验收报告：' + $report)
    Write-Host ('本次独立测试工具目录：' + $stage)
}
exit $result
