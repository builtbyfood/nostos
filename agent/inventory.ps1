# Nostos agent 0.2.3 - inventory.ps1
# Run by NostosAgent.exe as the logged-in user. Prints one JSON object:
# programs, mapped network drives, printers, fixed drives, Steam folder.
# Reads only; changes nothing. Every section is independent: if one cannot
# be read on this PC it is left empty and the rest still comes through.
$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$apps = @()
try {
    $keys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
    foreach ($k in $keys) {
        Get-ItemProperty $k | ForEach-Object {
            if ($_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName) {
                $apps += [string]$_.DisplayName
            }
        }
    }
} catch { }
try { Get-StartApps | ForEach-Object { $apps += [string]$_.Name } } catch { }
$apps = @($apps | Sort-Object -Unique)

$mapped = @()
try {
    Get-ChildItem 'HKCU:\Network' | ForEach-Object {
        $remote = (Get-ItemProperty $_.PSPath).RemotePath
        if ($remote) { $mapped += @{ letter = ($_.PSChildName.ToUpper() + ':'); path = [string]$remote } }
    }
} catch { }

$printers = @()
try { $printers = @(Get-Printer | ForEach-Object { [string]$_.Name }) } catch { }

$drives = @()
try {
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        $drives += @{ letter = [string]$_.DeviceID; label = [string]$_.VolumeName
                      size = [int64]$_.Size; free = [int64]$_.FreeSpace }
    }
} catch { }

$steam = ''
try { $steam = [string](Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath } catch { }
if (-not $steam) {
    try { $steam = [string](Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam').InstallPath } catch { }
}

$windows = ''
try { $windows = [string](Get-CimInstance Win32_OperatingSystem).Caption } catch { }

$result = [ordered]@{
    version       = 2
    computer      = [string]$env:COMPUTERNAME
    user          = [string]$env:USERNAME
    profile       = [string]$env:USERPROFILE
    windows       = $windows
    apps          = @($apps)
    mapped_drives = @($mapped)
    printers      = @($printers)
    drives        = @($drives)
    steam_path    = $steam
    wifi          = @()
}
$result | ConvertTo-Json -Depth 5 -Compress
