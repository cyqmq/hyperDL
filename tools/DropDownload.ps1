<#
.SYNOPSIS
    HyperDownloader — 拖拽下载 PowerShell 脚本
.DESCRIPTION
    将下载链接从浏览器拖拽到此脚本上即可下载。
    支持同时拖入多个链接文件。
#>

param(
    [string[]]$Urls
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

# 收集 URL
$urlList = @()

foreach ($item in $Urls) {
    if (-not $item) { continue }

    if (Test-Path $item -PathType Leaf) {
        # 如果是 .url 文件，提取 URL
        if ($item -like "*.url") {
            $content = Get-Content $item -Raw
            if ($content -match "URL=(.+\.exe|.+\.zip|.+\.msi|.+\.mp4|.+\.iso|.+\.7z|.+\.rar)") {
                $urlList += $matches[1]
            } elseif ($content -match "URL=(.+)") {
                $urlList += $matches[1]
            }
        } else {
            # 尝试作为文本文件读取 URL
            try {
                $lines = Get-Content $item
                foreach ($line in $lines) {
                    if ($line -match "https?://") {
                        $urlList += $line.Trim()
                    }
                }
            } catch {
                # 不是文件，可能是 URL 文本
                if ($item -match "https?://") {
                    $urlList += $item.Trim()
                }
            }
        }
    } elseif ($item -match "https?://") {
        $urlList += $item.Trim()
    }
}

if ($urlList.Count -eq 0) {
    Write-Log "╔══════════════════════════════════════════════╗" "DarkYellow"
    Write-Log "║  HyperDownloader — 拖拽下载                  ║" "DarkYellow"
    Write-Log "╠══════════════════════════════════════════════╣" "DarkYellow"
    Write-Log "║  请将下载链接从浏览器拖拽到此脚本上           ║" "DarkYellow"
    Write-Log "║  或运行: .\DropDownload.ps1 <URL>            ║" "DarkYellow"
    Write-Log "╚══════════════════════════════════════════════╝" "DarkYellow"
    pause
    exit
}

Write-Log "╔══════════════════════════════════════════════╗" "Cyan"
Write-Log "║  HyperDownloader Core — 拖拽下载              ║" "Cyan"
Write-Log "╚══════════════════════════════════════════════╝" "Cyan"
Write-Log ""

$downloadsDir = [Environment]::GetFolderPath("UserProfile") + "\Downloads"
Write-Log "📂 保存到: $downloadsDir" "Green"
Write-Log "🔗 共 $($urlList.Count) 个链接" "Green"
Write-Log ""

foreach ($url in $urlList) {
    Write-Log "  ▶ $url" "Yellow"
}

Write-Log ""
$confirm = Read-Host "开始下载? (Y/n)"
if ($confirm -eq "n" -or $confirm -eq "N") {
    exit
}

# 调用 Python 下载器
$pythonCmd = "py"
$scriptPath = Join-Path $scriptDir "drag_drop_downloader.py"

foreach ($url in $urlList) {
    Write-Log "`n开始下载: $url" "Cyan"
    & $pythonCmd "$scriptPath" --cli "$url"
}

Write-Log "`n✅ 全部完成!" "Green"
pause
