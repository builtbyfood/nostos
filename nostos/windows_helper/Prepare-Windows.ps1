# Nostos 0.2.4 - Prepare-Windows.ps1
# Run on the OLD Windows PC (double-click "Prepare this PC.cmd").
#
# What it does:
#   1. Writes a list of this user's programs, mapped network drives, printers
#      and saved Wi-Fi networks to  <profile>\NostosExport\manifest.json
#   2. Makes a temporary read-only account ("nostos") with a random password,
#      and shares this user's profile folder read-only as "Nostos".
#   3. Keeps the PC awake and waits. When you press Enter it removes the
#      account, the share and the export folder again.
#
# Nothing in the user's files is changed. Everything it sets up is undone at
# the end, or any time later with:  Prepare this PC.cmd  -Undo
#
# STATUS: UNVERIFIED on real hardware as of 0.2.4 (syntax-checked only).

param(
    [string]$ProfilePath = $env:USERPROFILE,
    [string]$UserName    = $env:USERNAME,
    [switch]$Elevated,
    [switch]$Undo,
    [switch]$NoWifi
)

$ErrorActionPreference = 'Stop'
$Account   = 'nostos'
$ShareName = 'Nostos'
$StateDir  = Join-Path $env:ProgramData 'Nostos'
$StateFile = Join-Path $StateDir 'state.json'
$ExportDir = Join-Path $ProfilePath 'NostosExport'
$Manifest  = Join-Path $ExportDir 'manifest.json'

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------------------------------------------------------------- phase 1 ---
# Runs as the normal user, so it sees THEIR programs and mapped drives.
function Export-Manifest {
    New-Item -ItemType Directory -Force -Path $ExportDir | Out-Null

    $apps = @()
    $keys = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')
    foreach ($k in $keys) {
        Get-ItemProperty $k -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.DisplayName -and -not $_.SystemComponent -and -not $_.ParentKeyName) {
                $apps += [string]$_.DisplayName
            }
        }
    }
    try {   # Store apps (Spotify, WhatsApp, iTunes are often installed this way)
        Get-StartApps | ForEach-Object { $apps += [string]$_.Name }
    } catch { }
    $apps = @($apps | Sort-Object -Unique)

    $drives = @()
    Get-ChildItem 'HKCU:\Network' -ErrorAction SilentlyContinue | ForEach-Object {
        $remote = (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).RemotePath
        if ($remote) {
            $drives += @{ letter = ($_.PSChildName.ToUpper() + ':'); path = [string]$remote }
        }
    }

    $printers = @()
    try { $printers = @(Get-Printer | ForEach-Object { [string]$_.Name }) } catch { }

    $data = [ordered]@{
        version       = 1
        computer      = $env:COMPUTERNAME
        user          = $UserName
        created       = (Get-Date).ToString('s')
        apps          = $apps
        mapped_drives = $drives
        printers      = $printers
        wifi          = @()
    }
    $data | ConvertTo-Json -Depth 5 | Set-Content -Path $Manifest -Encoding UTF8
    Say "  Found $($apps.Count) programs, $($drives.Count) network drives, $($printers.Count) printers."
}

# ---------------------------------------------------------------- phase 2 ---
function Add-WifiToManifest {
    $tmp = Join-Path $env:TEMP ('nostos-wifi-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        & netsh wlan export profile key=clear folder="$tmp" | Out-Null
        $wifi = @()
        Get-ChildItem $tmp -Filter *.xml -ErrorAction SilentlyContinue | ForEach-Object {
            [xml]$x = Get-Content $_.FullName -Encoding UTF8
            $p = $x.WLANProfile
            $sec = $p.MSM.security
            $wifi += @{
                ssid = [string]$p.SSIDConfig.SSID.name
                auth = [string]$sec.authEncryption.authentication
                key  = [string]$sec.sharedKey.keyMaterial
            }
        }
        if (Test-Path $Manifest) {
            $data = Get-Content $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
            $data.wifi = @($wifi)
            $data | ConvertTo-Json -Depth 5 | Set-Content -Path $Manifest -Encoding UTF8
        }
        Say "  Found $($wifi.Count) saved Wi-Fi networks."
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function New-Password {
    # No look-alike characters (0/O, 1/l/I) so it is easy to type.
    $upper = 'ABCDEFGHJKMNPQRSTUVWXYZ'.ToCharArray()
    $lower = 'abcdefghjkmnpqrstuvwxyz'.ToCharArray()
    $digit = '23456789'.ToCharArray()
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    $pick = {
        param($set)
        $b = New-Object byte[] 4
        $rng.GetBytes($b)
        $set[[BitConverter]::ToUInt32($b, 0) % $set.Length]
    }
    $parts = @()
    foreach ($i in 1..3) {
        $parts += (-join @((& $pick $upper), (& $pick $lower), (& $pick $lower), (& $pick $digit)))
    }
    $parts -join '-'
}

function Save-State($state) {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $state | ConvertTo-Json -Depth 5 | Set-Content -Path $StateFile -Encoding UTF8
}

function Start-Sharing {
    $state = @{ profile = $ProfilePath; networks = @(); firewall = @() }

    # Temporary account, hidden from the Windows sign-in screen.
    $plain = New-Password
    $secure = ConvertTo-SecureString $plain -AsPlainText -Force
    if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
        Set-LocalUser -Name $Account -Password $secure
        Enable-LocalUser -Name $Account
    } else {
        New-LocalUser -Name $Account -Password $secure -PasswordNeverExpires `
            -AccountNeverExpires -Description 'Temporary account for Nostos (safe to delete)' | Out-Null
    }
    $hide = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    New-Item -Path $hide -Force | Out-Null
    New-ItemProperty -Path $hide -Name $Account -Value 0 -PropertyType DWord -Force | Out-Null

    # Read-only access to this one profile folder.
    Say '  Allowing read-only access to your files (this can take a minute)...'
    & icacls "$ProfilePath" /grant "${Account}:(OI)(CI)RX" /C /Q | Out-Null

    if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) {
        Remove-SmbShare -Name $ShareName -Force
    }
    New-SmbShare -Name $ShareName -Path $ProfilePath -ReadAccess $Account `
        -Description 'Temporary share for Nostos' | Out-Null

    # Home networks marked "Public" block file sharing. Switch to Private and
    # remember, so Undo can put it back.
    Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' } | ForEach-Object {
        $state.networks += $_.InterfaceAlias
        Set-NetConnectionProfile -InterfaceAlias $_.InterfaceAlias -NetworkCategory Private
    }
    # File and Printer Sharing (SMB-In), by resource id so it works in any language.
    Get-NetFirewallRule -Group '@FirewallAPI.dll,-28502' -ErrorAction SilentlyContinue |
        Where-Object { $_.Enabled -eq 'False' -and $_.Direction -eq 'Inbound' -and
                       $_.Profile -match 'Private|Any' } | ForEach-Object {
            $state.firewall += $_.Name
            Enable-NetFirewallRule -Name $_.Name
        }
    Set-Service -Name LanmanServer -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service -Name LanmanServer -ErrorAction SilentlyContinue

    Save-State $state
    return $plain
}

function Stop-Sharing {
    $state = $null
    if (Test-Path $StateFile) {
        $state = Get-Content $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    $profileDir = if ($state -and $state.profile) { $state.profile } else { $ProfilePath }

    if (Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue) {
        Remove-SmbShare -Name $ShareName -Force
    }
    if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
        & icacls "$profileDir" /remove "$Account" /C /Q | Out-Null
        Remove-LocalUser -Name $Account
    }
    $hide = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\SpecialAccounts\UserList'
    Remove-ItemProperty -Path $hide -Name $Account -ErrorAction SilentlyContinue
    if ($state) {
        foreach ($name in @($state.firewall)) {
            if ($name) { Disable-NetFirewallRule -Name $name -ErrorAction SilentlyContinue }
        }
        foreach ($alias in @($state.networks)) {
            if ($alias) {
                Set-NetConnectionProfile -InterfaceAlias $alias -NetworkCategory Public `
                    -ErrorAction SilentlyContinue
            }
        }
    }
    # The export holds Wi-Fi passwords, so it must not be left behind.
    Remove-Item (Join-Path $profileDir 'NostosExport') -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $StateDir -Recurse -Force -ErrorAction SilentlyContinue
}

function Keep-Awake([bool]$on) {
    try {
        if (-not ('Nostos.Power' -as [type])) {
            Add-Type -Namespace Nostos -Name Power -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
'@
        }
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED   /   ES_CONTINUOUS
        $flags = if ($on) { [uint32]2147483649 } else { [uint32]2147483648 }
        [Nostos.Power]::SetThreadExecutionState($flags) | Out-Null
    } catch { }
}

# -------------------------------------------------------------------- main ---
try {
    if (-not $Elevated) {
        Clear-Host
        Say ''
        Say '  Nostos helper - getting this PC ready to move to Linux' 'Cyan'
        Say ''
        if (-not $Undo) {
            Say '  Looking at what is on this PC...'
            Export-Manifest
        }
        Say '  Windows will now ask for permission to continue. Choose Yes.'
        $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                     '-Elevated', '-ProfilePath', "`"$ProfilePath`"", '-UserName', "`"$UserName`"")
        if ($Undo)   { $argList += '-Undo' }
        if ($NoWifi) { $argList += '-NoWifi' }
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs
        exit 0
    }

    if (-not (Test-Admin)) { throw 'This step needs administrator permission.' }

    if ($Undo) {
        Stop-Sharing
        Say ''
        Say '  Everything Nostos set up on this PC has been removed.' 'Green'
        Say ''
        Read-Host '  Press Enter to close' | Out-Null
        exit 0
    }

    if (-not $NoWifi) { Add-WifiToManifest }
    $password = Start-Sharing
    Keep-Awake $true

    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and
                       $_.PrefixOrigin -ne 'WellKnown' } |
        ForEach-Object { $_.IPAddress })

    Say ''
    Say '  ============================================================' 'Green'
    Say '   This PC is ready. Type these into Nostos on the new computer:' 'Green'
    Say '  ============================================================' 'Green'
    Say ''
    Say ("   Windows PC :  {0}    (or  {1})" -f $env:COMPUTERNAME, ($addresses -join '  or  ')) 'White'
    Say ("   User name  :  {0}" -f $Account) 'White'
    Say ("   Password   :  {0}" -f $password) 'Yellow'
    Say ''
    Say '   Leave this window open and the PC plugged in until the move is done.'
    Say '   Files that live only in OneDrive (cloud icon) are not on this PC;'
    Say '   connect OneDrive in Nostos to get those.'
    Say ''
    Read-Host '  When the move has finished, press Enter here to clean up' | Out-Null

    Keep-Awake $false
    Stop-Sharing
    Say ''
    Say '  Done. The temporary account and share have been removed.' 'Green'
    Say ''
    Read-Host '  Press Enter to close' | Out-Null
}
catch {
    Say ''
    Say "  Something went wrong: $($_.Exception.Message)" 'Red'
    Say "  ($($_.InvocationInfo.PositionMessage))" 'DarkGray'
    Say ''
    Say '  Nothing in your files was changed. To remove anything that was set up,'
    Say '  run:  "Prepare this PC.cmd" -Undo'
    Say ''
    Read-Host '  Press Enter to close' | Out-Null
    exit 1
}
