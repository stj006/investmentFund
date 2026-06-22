# 通过 GitHub API 触发 workflow_dispatch（供本地测试 / cron-job 对照）
param(
    [ValidateSet("daily", "weekly")]
    [string]$Workflow = "daily"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+?)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            if (-not [Environment]::GetEnvironmentVariable($name)) {
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

$pat = $env:GITHUB_PAT
if (-not $pat) {
    Write-Error "请在 .env 设置 GITHUB_PAT=你的 Fine-grained Token（Actions: write）"
}

$file = if ($Workflow -eq "weekly") { "weekly_recommend.yml" } else { "daily_report.yml" }
$url = "https://api.github.com/repos/stj001/investmentFund/actions/workflows/$file/dispatches"
$body = '{"ref":"master"}'

Write-Host "触发: $file"
$response = Invoke-WebRequest -Uri $url -Method POST `
    -Headers @{
        Accept = "application/vnd.github+json"
        Authorization = "Bearer $pat"
        "X-GitHub-Api-Version" = "2022-11-28"
    } `
    -Body $body `
    -ContentType "application/json" `
    -UseBasicParsing

if ($response.StatusCode -eq 204) {
    Write-Host "成功 (HTTP 204)。请到 GitHub Actions 查看运行状态。"
} else {
    Write-Host "HTTP $($response.StatusCode): $($response.Content)"
}
